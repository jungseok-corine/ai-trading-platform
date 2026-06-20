"""C-2.53 전체 분석 번들(테이프+매크로+뉴스+노트) 합본 테스트."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, MarketCode, OrderStatus, TradeSide
from app.domain.models.market_data import MarketData
from app.domain.models.news_context import UsMarketSnapshot
from app.domain.models.trade import Trade
from app.main import app
from app.services.analysis_bundle_service import AnalysisBundleService
from app.services.news_context_service import NewsContextService
from app.services.strategy_service import StrategyService

KST = ZoneInfo("Asia/Seoul")
DAY = date(2026, 6, 17)
T0 = datetime(2026, 6, 17, 9, 0, tzinfo=KST)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _seed(session: AsyncSession) -> int:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    session.add(account)
    await session.commit()
    svc = StrategyService(session)
    strategy = await svc.create_strategy("bundle-strat")
    version = await svc.create_version(strategy.id, parameters={"symbol_code": "005930"})

    for i in range(20):
        px = Decimal("100") + Decimal(i) / 10
        session.add(MarketData(symbol_code="005930", timeframe="1m",
                               ts=T0 + timedelta(minutes=i), open=px, high=px + 1,
                               low=px - 1, close=px, volume=1000))
    session.add(Trade(account_id=account.id, strategy_version_id=version.id,
                      symbol_code="005930", side=TradeSide.BUY, quantity=10,
                      entry_time=T0 + timedelta(minutes=5), exit_time=T0 + timedelta(minutes=15),
                      entry_price=Decimal("100.5"), exit_price=Decimal("101.4"),
                      pnl_amount=Decimal("9"), pnl_pct=Decimal("0.9"),
                      order_status=OrderStatus.FILLED))
    # 전일 미국장 (매크로 risk_off)
    session.add(UsMarketSnapshot(session_date=date(2026, 6, 16), vix=Decimal("31.0"),
                                 nasdaq_change_pct=Decimal("-1.8")))
    # 종목 뉴스(수동 주입)
    await NewsContextService(session).create_news(
        headline="삼성전자 신제품 공개", published_at=T0, market=MarketCode.KR,
        symbol_code="005930", source="manual", sentiment="positive",
    )
    await session.commit()
    return version.id


async def test_full_bundle_composes_all_parts(db_session: AsyncSession) -> None:
    vid = await _seed(db_session)
    bundle = await AnalysisBundleService(db_session).build_full(
        vid, DAY, analyst_note="오늘 반도체 강세 주목"
    )
    assert bundle is not None
    assert bundle["meta"]["symbol_code"] == "005930"
    # 매매 테이프
    assert bundle["trade_tape"]["meta"]["trade_count"] == 1
    assert "mfe_pct" in bundle["trade_tape"]["trades"][0]["features"]
    # 매크로
    assert bundle["macro"]["regime"] == "risk_off"
    # 뉴스 (수동 주입 포함)
    assert len(bundle["news"]) == 1
    assert bundle["news"][0]["sentiment"] == "positive"
    # 전략 입력 + 수동 노트
    assert bundle["strategy_input"] is not None
    assert bundle["analyst_note"] == "오늘 반도체 강세 주목"


async def test_full_bundle_unknown_version_is_none(db_session: AsyncSession) -> None:
    assert await AnalysisBundleService(db_session).build_full(999999, DAY) is None


async def test_full_bundle_via_api(db_session: AsyncSession) -> None:
    vid = await _seed(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/analysis-bundle/full", params={
                "strategy_version_id": vid, "trading_day": "2026-06-17",
                "analyst_note": "체크",
            })
            assert resp.status_code == 200
            body = resp.json()
            assert body["macro"]["regime"] == "risk_off"
            assert body["analyst_note"] == "체크"
            assert body["trade_tape"]["meta"]["trade_count"] == 1
    finally:
        app.dependency_overrides.clear()
