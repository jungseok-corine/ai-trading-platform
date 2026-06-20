"""C-2.57 뉴스 중요도 큐레이션 테스트."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.services.news_context_service import NewsContextService
from app.services.news_curator_service import NewsCuratorService
from app.trading.analysis.news_materiality import (
    CATEGORY_HIGH,
    CATEGORY_MEDIUM,
    CATEGORY_NOISE,
    is_material,
    score_materiality,
)

KST = ZoneInfo("Asia/Seoul")
T = datetime(2026, 6, 18, 9, 0, tzinfo=KST)


# --- 순수 점수 --------------------------------------------------------------
def test_score_high_medium_noise() -> None:
    assert score_materiality("삼성전자 1300억 규모 단일판매·공급계약 체결")[1] == CATEGORY_HIGH
    assert score_materiality("신제품 출시 예정")[1] == CATEGORY_MEDIUM
    assert score_materiality("[기재정정] IR 일정 안내")[1] == CATEGORY_NOISE


def test_high_keyword_beats_noise() -> None:
    # 중요 공시의 '정정'이라도 고중요로 본다(유상증자 결정 정정)
    assert score_materiality("유상증자 결정 정정")[1] == CATEGORY_HIGH


def test_is_material_threshold() -> None:
    assert is_material("자기주식 취득 결정") is True
    assert is_material("[정정] IR 일정") is False


# --- 큐레이터 서비스 --------------------------------------------------------
async def _add(session, headline, sentiment=None, themes=None):
    await NewsContextService(session).create_news(
        headline=headline, published_at=T, market=MarketCode.KR,
        symbol_code="005930", source="manual", sentiment=sentiment, themes=themes,
    )


async def test_curate_filters_noise_and_ranks(db_session: AsyncSession) -> None:
    await _add(db_session, "삼성전자 대규모 공급계약 체결", sentiment="positive")  # high 0.9
    await _add(db_session, "신제품 갤럭시 공개")  # medium 0.6
    await _add(db_session, "[기재정정] 정기주총 일정 안내")  # noise 0.15 → 제외

    curated = await NewsCuratorService(db_session).curate(symbol_code="005930", min_score=0.5)
    assert len(curated) == 2  # noise 제외
    # 중요도순: 공급계약(high) 먼저
    assert curated[0]["category"] == CATEGORY_HIGH
    assert "공급계약" in curated[0]["headline"]
    assert curated[1]["category"] == CATEGORY_MEDIUM
    assert all(c["materiality"] >= 0.5 for c in curated)


async def test_bundle_uses_curated_news(db_session: AsyncSession) -> None:
    from datetime import date, timedelta
    from decimal import Decimal

    from app.domain.models.market_data import MarketData
    from app.services.analysis_bundle_service import AnalysisBundleService
    from app.services.strategy_service import StrategyService

    svc = StrategyService(db_session)
    strategy = await svc.create_strategy("curate")
    version = await svc.create_version(strategy.id, parameters={"symbol_code": "005930"})
    for i in range(5):
        px = Decimal("100") + Decimal(i) / 10
        db_session.add(MarketData(symbol_code="005930", timeframe="1m",
                                  ts=T + timedelta(minutes=i), open=px, high=px + 1,
                                  low=px - 1, close=px, volume=1000))
    await _add(db_session, "자사주 매입 결정", sentiment="positive")  # high
    await _add(db_session, "[정정] IR 일정")  # noise → 제외
    await db_session.commit()

    bundle = await AnalysisBundleService(db_session).build_full(version.id, date(2026, 6, 18))
    assert len(bundle["news"]) == 1  # 노이즈 제외
    assert bundle["news"][0]["category"] == CATEGORY_HIGH
