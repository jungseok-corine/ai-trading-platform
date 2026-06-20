"""C-2.52 매매 테이프(분봉 압축 + 사전계산 + 압축손실 가드) 테스트."""

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
from app.trading.analysis.trade_tape import (
    Candle,
    TradeEvent,
    build_trade_tape,
    detect_notable,
    mfe_mae,
    range_percentile,
    vwap,
)

KST = ZoneInfo("Asia/Seoul")
DAY = date(2026, 6, 17)
T0 = datetime(2026, 6, 17, 9, 0, tzinfo=KST)


def _c(minute: int, o, h, lo, cl, v) -> Candle:
    return Candle(ts=T0 + timedelta(minutes=minute), o=o, h=h, lo=lo, c=cl, v=v)


# --- 순수 함수 --------------------------------------------------------------
def test_vwap_and_range_percentile() -> None:
    candles = [_c(0, 100, 102, 99, 101, 100), _c(1, 101, 103, 100, 102, 300)]
    assert vwap(candles) is not None
    assert range_percentile(102, 99, 103) == 75.0
    assert range_percentile(99, 99, 103) == 0.0


def test_mfe_mae_long() -> None:
    candles = [_c(0, 100, 100, 100, 100, 10), _c(1, 100, 106, 98, 104, 10)]
    mfe, mae = mfe_mae(candles, 0, 1, entry_price=100.0, side="buy")
    assert mfe == 6.0  # 고가 106 → +6%
    assert mae == -2.0  # 저가 98 → -2%


def test_detect_notable_catches_offtrade_spike() -> None:
    # 평탄한 하루 중 13:00 한 캔들만 거래량/변동 급증 → notable로 잡혀야 함
    candles = [_c(i, 100, 100.2, 99.8, 100, 100) for i in range(30)]
    candles[20] = _c(20, 100, 112, 100, 111, 5000)  # 큰 변동 + 거래량 급증
    notable = detect_notable(candles)
    assert any(n["index"] == 20 for n in notable)


def test_build_tape_keeps_notable_outside_trade_window() -> None:
    # 매매는 09:02에만, 급등은 09:25에. 압축해도 09:25가 detailed에 살아있어야 한다(가드).
    candles = [_c(i, 100, 100.1, 99.9, 100, 100) for i in range(40)]
    candles[25] = _c(25, 100, 110, 100, 109, 4000)
    trades = [TradeEvent(side="buy", quantity=1, entry_time=T0 + timedelta(minutes=2),
                         entry_price=100.0, pnl_pct=0.5)]
    tape = build_trade_tape(candles, trades, window=3, coarse=10)

    detailed_ts = {d["ts"] for d in tape["detailed_candles"]}
    assert candles[25].ts.isoformat() in detailed_ts  # 매매 밖 급등도 상세 유지
    assert tape["audit"]["notable_events"] >= 1
    assert tape["audit"]["candles_total"] == 40
    # 압축 효과: 상세 < 전체
    assert tape["audit"]["candles_detailed"] < 40
    # 사전계산 특징 존재
    assert "features" in tape["trades"][0]
    assert "mfe_pct" in tape["trades"][0]["features"]


# --- 서비스 / API -----------------------------------------------------------
def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _seed(session: AsyncSession) -> int:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    session.add(account)
    await session.commit()
    svc = StrategyService(session)
    strategy = await svc.create_strategy("tape-strat")
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


async def test_service_builds_tape(db_session: AsyncSession) -> None:
    vid = await _seed(db_session)
    tape = await TradeTapeService(db_session).build_for_version(vid, DAY)
    assert tape is not None
    assert tape["meta"]["symbol_code"] == "005930"
    assert tape["meta"]["trade_count"] == 1
    assert tape["day_summary"]["candle_count"] == 30
    assert tape["trades"][0]["features"]["realized_return_pct"] == 1.49


async def test_service_unknown_version_is_none(db_session: AsyncSession) -> None:
    assert await TradeTapeService(db_session).build_for_version(999999, DAY) is None


async def test_tape_via_api(db_session: AsyncSession) -> None:
    vid = await _seed(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/analysis-bundle/trade-tape",
                                    params={"strategy_version_id": vid, "trading_day": "2026-06-17"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["meta"]["trade_count"] == 1
            assert "audit" in body

            missing = await client.get("/api/v1/analysis-bundle/trade-tape",
                                       params={"strategy_version_id": 999999, "trading_day": "2026-06-17"})
            assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
