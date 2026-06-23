"""C-5.21: 미장 분석 번들에 US 공시(EDGAR) 주입 + 분석 시장 추론.

EDGAR 공시는 영어 헤드라인([8-K] …)이라 한국어 키워드 채점기로 다시 매기면 떨어진다.
수집 시 저장한 중요도(raw_payload.materiality)를 우선해 미장 분석 번들까지 살아남는지 검증.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.models.market_data import MarketData
from app.services.analysis_bundle_service import (
    AnalysisBundleService,
    resolve_analysis_market,
)
from app.services.news_context_service import NewsContextService
from app.services.news_curator_service import NewsCuratorService
from app.services.strategy_service import StrategyService

KST = ZoneInfo("Asia/Seoul")
T = datetime(2026, 6, 18, 9, 0, tzinfo=KST)


# --- 분석 시장 추론(순수) ---------------------------------------------------
def test_resolve_analysis_market() -> None:
    assert resolve_analysis_market({"market": "US"}) == MarketCode.US
    assert resolve_analysis_market({"universe": "watchlist", "universe_market": "US"}) == MarketCode.US
    assert resolve_analysis_market({"market": "KR"}) == MarketCode.KR
    assert resolve_analysis_market({}) == MarketCode.KR  # 미지정/혼합 → KR(하위호환)


async def _add_edgar(session, headline, materiality, category) -> None:
    await NewsContextService(session).create_news(
        headline=headline, published_at=T, market=MarketCode.US,
        symbol_code="AAPL", source="edgar",
        url=f"https://sec.gov/{headline}",
        raw_payload={"materiality": materiality, "category": category, "form": "8-K"},
    )


# --- 큐레이터: 영어 EDGAR 헤드라인 생존 -------------------------------------
async def test_curate_keeps_edgar_via_stored_score(db_session: AsyncSession) -> None:
    await _add_edgar(db_session, "[8-K] Apple Inc.", 0.9, "high")     # high
    await _add_edgar(db_session, "[4] Apple Inc.", 0.3, "low")        # low → 제외(min 0.5)

    curated = await NewsCuratorService(db_session).curate(
        market=MarketCode.US, symbol_code="AAPL", min_score=0.5
    )
    # 한국어 채점기였다면 둘 다 떨어졌을 것 — 저장된 중요도로 8-K만 생존.
    assert len(curated) == 1
    assert curated[0]["category"] == "high"
    assert "8-K" in curated[0]["headline"]
    assert curated[0]["source"] == "edgar"


# --- 번들: universe 전략(symbol_code 없음)도 시장 수준 뉴스를 받는다 ------
async def test_bundle_universe_strategy_gets_market_news(db_session: AsyncSession) -> None:
    svc = StrategyService(db_session)
    strategy = await svc.create_strategy("us-universe")
    version = await svc.create_version(
        strategy.id,
        parameters={"universe": "watchlist", "universe_market": "US"},  # symbol_code 없음
    )
    await _add_edgar(db_session, "[8-K] Tesla Inc.", 0.85, "high")
    await db_session.commit()

    bundle = await AnalysisBundleService(db_session).build_full(version.id, date(2026, 6, 18))
    assert bundle is not None
    assert bundle["meta"]["market"] == MarketCode.US.value
    assert bundle["meta"]["symbol_code"] == ""  # 하위호환: 빈 문자열 보존
    # symbol_code 없어도 시장 수준 뉴스 수집됨
    assert len(bundle["news"]) == 1
    assert bundle["news"][0]["source"] == "edgar"


# --- 번들: US 전략은 market 미지정이어도 US 공시를 받는다 -------------------
async def test_bundle_us_strategy_injects_edgar(db_session: AsyncSession) -> None:
    svc = StrategyService(db_session)
    strategy = await svc.create_strategy("us-edgar")
    version = await svc.create_version(
        strategy.id, parameters={"symbol_code": "AAPL", "market": "US"}
    )
    for i in range(5):
        px = Decimal("100") + Decimal(i) / 10
        db_session.add(MarketData(symbol_code="AAPL", timeframe="1m",
                                  ts=T + timedelta(minutes=i), open=px, high=px + 1,
                                  low=px - 1, close=px, volume=1000))
    await _add_edgar(db_session, "[8-K] Apple Inc.", 0.9, "high")
    await db_session.commit()

    # market 미지정 → 전략 파라미터(market=US)에서 US로 추론.
    bundle = await AnalysisBundleService(db_session).build_full(version.id, date(2026, 6, 18))
    assert bundle["meta"]["market"] == MarketCode.US.value
    assert len(bundle["news"]) == 1
    assert bundle["news"][0]["source"] == "edgar"
