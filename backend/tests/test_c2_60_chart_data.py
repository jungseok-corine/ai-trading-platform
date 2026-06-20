"""C-2.60 차트 데이터(전체 캔들 + 매매 마커) 테스트."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.market_data import MarketData
from app.domain.models.trade import Trade
from app.main import app
from app.services.strategy_service import StrategyService
from app.services.trade_tape_service import TradeTapeService

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
    strategy = await svc.create_strategy("chart")
    version = await svc.create_version(strategy.id, parameters={"symbol_code": "005930"})
    for i in range(30):
        px = Decimal("100") + Decimal(i) / 10
        session.add(MarketData(symbol_code="005930", timeframe="1m",
                               ts=T0 + timedelta(minutes=i), open=px, high=px + 1,
                               low=px - 1, close=px, volume=1000))
    session.add(Trade(account_id=account.id, strategy_version_id=version.id,
                      symbol_code="005930", side=TradeSide.BUY, quantity=10,
                      entry_time=T0 + timedelta(minutes=5), exit_time=T0 + timedelta(minutes=20),
                      entry_price=Decimal("100.5"), exit_price=Decimal("102.0"),
                      pnl_amount=Decimal("15"), pnl_pct=Decimal("1.49"),
                      order_status=OrderStatus.FILLED))
    await session.commit()
    return version.id


async def test_chart_data_has_candles_and_markers(db_session: AsyncSession) -> None:
    vid = await _seed(db_session)
    data = await TradeTapeService(db_session).build_chart_data(vid, DAY)
    assert data is not None
    assert data["symbol_code"] == "005930"
    assert len(data["candles"]) == 30
    # 진입 + 청산 마커 2개
    kinds = sorted(m["kind"] for m in data["markers"])
    assert kinds == ["entry", "exit"]
    assert data["markers"][0]["side"] == "buy"


async def test_chart_data_via_api(db_session: AsyncSession) -> None:
    vid = await _seed(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/analysis-bundle/chart-data", params={
                "strategy_version_id": vid, "trading_day": "2026-06-17"})
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["candles"]) == 30
            assert len(body["markers"]) == 2
    finally:
        app.dependency_overrides.clear()
