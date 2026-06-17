"""Strategy Performance Metrics (Phase C-1) 통합 테스트."""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.market_data import MarketData
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade
from app.main import app
from app.services.strategy_performance_service import StrategyPerformanceService

KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ts(minute: int, hour: int = 9) -> datetime:
    return datetime(2026, 6, 10, hour, minute, 0, tzinfo=KST)


def _candle(
    session: AsyncSession,
    symbol: str = "005930",
    tf: str = "1m",
    minute: int = 0,
    hour: int = 9,
    open_: int = 100,
    high: int = 110,
    low: int = 90,
    close: int = 105,
) -> MarketData:
    return MarketData(
        symbol_code=symbol,
        timeframe=tf,
        ts=_ts(minute, hour=hour),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=1000,
    )


async def _add_strategy_version(
    session: AsyncSession,
    symbol: str = "005930",
) -> tuple[Strategy, StrategyVersion]:
    strat = Strategy(name="perf-test", description="")
    session.add(strat)
    await session.flush()
    ver = StrategyVersion(
        strategy_id=strat.id,
        version_no=1,
        parameters={"strategy_type": "moving_average_cross", "symbol_code": symbol},
    )
    session.add(ver)
    await session.flush()
    return strat, ver


async def _add_signal(
    session: AsyncSession,
    version_id: int,
    signal_type: TradeSide = TradeSide.BUY,
    candle_ts: datetime | None = None,
    symbol: str = "005930",
) -> SignalLog:
    sig = SignalLog(
        symbol_code=symbol,
        strategy_version_id=version_id,
        signal_type=signal_type,
        generated_at=datetime.now(KST),
        candle_ts=candle_ts or _ts(30),
    )
    session.add(sig)
    await session.flush()
    return sig


async def _add_account(session: AsyncSession) -> Account:
    acct = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    session.add(acct)
    await session.flush()
    return acct


async def _add_trade(
    session: AsyncSession,
    account_id: int,
    version_id: int,
    pnl_amount: Decimal | None = None,
    status: OrderStatus = OrderStatus.FILLED,
    side: TradeSide = TradeSide.BUY,
) -> Trade:
    trade = Trade(
        account_id=account_id,
        strategy_version_id=version_id,
        symbol_code="005930",
        side=side,
        quantity=1,
        order_status=status,
        pnl_amount=pnl_amount,
    )
    session.add(trade)
    await session.flush()
    return trade


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


import pytest


@pytest.fixture(autouse=True)
def _db_override(db_session: AsyncSession):
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    yield
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 1. version not found / wrong strategy
# ---------------------------------------------------------------------------


async def test_performance_version_not_found(db_session: AsyncSession) -> None:
    """존재하지 않는 version_id → None."""
    svc = StrategyPerformanceService(db_session)
    result = await svc.get_version_performance(strategy_id=1, version_id=99999)
    assert result is None


async def test_performance_version_wrong_strategy(db_session: AsyncSession) -> None:
    """version_id는 존재하지만 strategy_id가 다르면 None."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyPerformanceService(db_session)
    result = await svc.get_version_performance(strategy_id=strat.id + 999, version_id=ver.id)
    assert result is None


# ---------------------------------------------------------------------------
# 2. 신호 없는 version → 빈 성과
# ---------------------------------------------------------------------------


async def test_performance_no_signals(db_session: AsyncSession) -> None:
    """신호가 없는 전략 버전은 zero 집계를 반환한다."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyPerformanceService(db_session)
    perf = await svc.get_version_performance(strat.id, ver.id)

    assert perf is not None
    assert perf.total_signals == 0
    assert perf.analyzed_signals == 0
    assert perf.skipped_signals == 0
    assert perf.by_signal_type == []
    assert perf.by_symbol == []
    for h in perf.by_horizon:
        assert h.count == 0
        assert h.avg_mfe_pct is None


# ---------------------------------------------------------------------------
# 3. 신호 필터링 — 다른 버전 신호 제외
# ---------------------------------------------------------------------------


async def test_only_signals_for_this_version_counted(db_session: AsyncSession) -> None:
    """다른 strategy_version의 신호는 집계에 포함되지 않는다."""
    strat, ver_a = await _add_strategy_version(db_session)
    ver_b = StrategyVersion(
        strategy_id=strat.id,
        version_no=2,
        parameters={"strategy_type": "moving_average_cross", "symbol_code": "005930"},
    )
    db_session.add(ver_b)
    await db_session.flush()

    # ver_a: 신호 1개 + market_data 있음
    await _add_signal(db_session, ver_a.id, candle_ts=_ts(10))
    db_session.add(_candle(db_session, minute=11, open_=100, close=110))

    # ver_b: 신호 2개
    await _add_signal(db_session, ver_b.id, candle_ts=_ts(20))
    await _add_signal(db_session, ver_b.id, candle_ts=_ts(25))
    await db_session.flush()

    svc = StrategyPerformanceService(db_session)
    perf_a = await svc.get_version_performance(strat.id, ver_a.id)
    perf_b = await svc.get_version_performance(strat.id, ver_b.id)

    assert perf_a.total_signals == 1
    assert perf_b.total_signals == 2


# ---------------------------------------------------------------------------
# 4. market_data 부족 → skipped_count
# ---------------------------------------------------------------------------


async def test_skipped_signals_no_market_data(db_session: AsyncSession) -> None:
    """market_data가 없는 신호는 skipped로 집계된다."""
    strat, ver = await _add_strategy_version(db_session)
    await _add_signal(db_session, ver.id, candle_ts=_ts(30))
    # market_data 없음

    svc = StrategyPerformanceService(db_session)
    perf = await svc.get_version_performance(strat.id, ver.id)

    assert perf.total_signals == 1
    assert perf.analyzed_signals == 0
    assert perf.skipped_signals == 1


# ---------------------------------------------------------------------------
# 5. horizon별 win_rate / avg_directional_return_pct
# ---------------------------------------------------------------------------


async def test_horizon_win_rate_buy_wins(db_session: AsyncSession) -> None:
    """BUY 신호 이후 가격 상승 → 5분 win_rate=1.0."""
    strat, ver = await _add_strategy_version(db_session)
    await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(10))
    db_session.add(_candle(db_session, minute=11, open_=100, close=100))
    db_session.add(_candle(db_session, minute=15, close=120))  # +20%
    await db_session.flush()

    svc = StrategyPerformanceService(db_session)
    perf = await svc.get_version_performance(strat.id, ver.id)

    h5 = next(h for h in perf.by_horizon if h.horizon_minutes == 5)
    assert h5.count == 1
    assert h5.win_rate == Decimal("1.0000")
    assert h5.avg_return_pct == Decimal("20.0000")
    assert h5.avg_directional_return_pct == Decimal("20.0000")  # BUY: same as return


async def test_horizon_avg_directional_return_sell_win(db_session: AsyncSession) -> None:
    """SELL 신호 이후 가격 하락 → directional_return_pct 양수, win_rate=1.0."""
    strat, ver = await _add_strategy_version(db_session)
    await _add_signal(db_session, ver.id, TradeSide.SELL, candle_ts=_ts(10))
    db_session.add(_candle(db_session, minute=11, open_=100, close=100))
    db_session.add(_candle(db_session, minute=15, close=80))  # -20%
    await db_session.flush()

    svc = StrategyPerformanceService(db_session)
    perf = await svc.get_version_performance(strat.id, ver.id)

    h5 = next(h for h in perf.by_horizon if h.horizon_minutes == 5)
    assert h5.count == 1
    assert h5.win_rate == Decimal("1.0000")
    assert h5.avg_return_pct == Decimal("-20.0000")          # raw: 하락
    assert h5.avg_directional_return_pct == Decimal("20.0000")  # SELL: 방향 반전


async def test_horizon_avg_mfe_mae(db_session: AsyncSession) -> None:
    """BUY 신호: avg_mfe_pct = (max_high - entry) / entry * 100."""
    strat, ver = await _add_strategy_version(db_session)
    await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(10))
    # entry=100, high최대=130, low최소=80
    db_session.add(_candle(db_session, minute=11, open_=100, high=110, low=95, close=105))
    db_session.add(_candle(db_session, minute=15, high=130, low=80, close=105))
    await db_session.flush()

    svc = StrategyPerformanceService(db_session)
    perf = await svc.get_version_performance(strat.id, ver.id)

    h5 = next(h for h in perf.by_horizon if h.horizon_minutes == 5)
    assert h5.avg_mfe_pct == Decimal("30.0000")  # (130-100)/100*100
    assert h5.avg_mae_pct == Decimal("20.0000")  # (100-80)/100*100


# ---------------------------------------------------------------------------
# 6. by_signal_type 집계
# ---------------------------------------------------------------------------


async def test_by_signal_type_buy_sell(db_session: AsyncSession) -> None:
    """BUY/SELL 신호가 각각 by_signal_type으로 분리 집계된다."""
    strat, ver = await _add_strategy_version(db_session)

    # BUY 신호 + data
    await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(10))
    db_session.add(_candle(db_session, minute=11, open_=100, close=100))
    db_session.add(_candle(db_session, minute=15, close=110))

    # SELL 신호 (no market_data → skipped)
    await _add_signal(db_session, ver.id, TradeSide.SELL, candle_ts=_ts(20))
    await db_session.flush()

    svc = StrategyPerformanceService(db_session)
    perf = await svc.get_version_performance(strat.id, ver.id)

    by_type = {item.signal_type: item for item in perf.by_signal_type}
    assert TradeSide.BUY in by_type
    assert by_type[TradeSide.BUY].signal_count == 1
    assert by_type[TradeSide.BUY].analyzed_count == 1
    assert by_type[TradeSide.BUY].win_rate_5m == Decimal("1.0000")

    assert TradeSide.SELL in by_type
    assert by_type[TradeSide.SELL].signal_count == 1
    assert by_type[TradeSide.SELL].analyzed_count == 0  # skipped
    assert by_type[TradeSide.SELL].win_rate_5m is None


async def test_by_signal_type_empty_if_only_one_side(db_session: AsyncSession) -> None:
    """BUY 신호만 있으면 by_signal_type에 SELL 항목이 없다."""
    strat, ver = await _add_strategy_version(db_session)
    await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(10))
    await db_session.flush()

    svc = StrategyPerformanceService(db_session)
    perf = await svc.get_version_performance(strat.id, ver.id)

    types = {item.signal_type for item in perf.by_signal_type}
    assert TradeSide.BUY in types
    assert TradeSide.SELL not in types


# ---------------------------------------------------------------------------
# 7. by_symbol 집계
# ---------------------------------------------------------------------------


async def test_by_symbol_grouping(db_session: AsyncSession) -> None:
    """서로 다른 종목 신호가 종목별로 분리 집계된다."""
    strat, ver = await _add_strategy_version(db_session)

    # 005930 신호 + data
    await _add_signal(db_session, ver.id, symbol="005930", candle_ts=_ts(10))
    db_session.add(_candle(db_session, symbol="005930", minute=11, open_=100, close=100))
    db_session.add(_candle(db_session, symbol="005930", minute=15, close=110))

    # 035420 신호 (no data → skipped)
    await _add_signal(db_session, ver.id, symbol="035420", candle_ts=_ts(10))
    await db_session.flush()

    svc = StrategyPerformanceService(db_session)
    perf = await svc.get_version_performance(strat.id, ver.id)

    by_sym = {item.symbol_code: item for item in perf.by_symbol}
    assert "005930" in by_sym
    assert by_sym["005930"].signal_count == 1
    assert by_sym["005930"].analyzed_count == 1
    assert by_sym["005930"].win_rate_5m == Decimal("1.0000")

    assert "035420" in by_sym
    assert by_sym["035420"].signal_count == 1
    assert by_sym["035420"].analyzed_count == 0
    assert by_sym["035420"].win_rate_5m is None


# ---------------------------------------------------------------------------
# 8. 실제 체결 성과
# ---------------------------------------------------------------------------


async def test_actual_trading_no_trades(db_session: AsyncSession) -> None:
    """체결 기록이 없으면 actual_trading에서 filled_count=0, pnl=None."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyPerformanceService(db_session)
    perf = await svc.get_version_performance(strat.id, ver.id)

    assert perf.actual_trading is not None
    assert perf.actual_trading.trade_count == 0
    assert perf.actual_trading.filled_count == 0
    assert perf.actual_trading.total_pnl_amount is None


async def test_actual_trading_filled_pnl_summed(db_session: AsyncSession) -> None:
    """체결 완료된 trade의 pnl_amount가 합산된다."""
    strat, ver = await _add_strategy_version(db_session)
    acct = await _add_account(db_session)

    await _add_trade(db_session, acct.id, ver.id, pnl_amount=Decimal("1000"), status=OrderStatus.FILLED)
    await _add_trade(db_session, acct.id, ver.id, pnl_amount=Decimal("-500"), status=OrderStatus.FILLED)
    await _add_trade(db_session, acct.id, ver.id, pnl_amount=None, status=OrderStatus.PENDING)  # excluded from pnl

    svc = StrategyPerformanceService(db_session)
    perf = await svc.get_version_performance(strat.id, ver.id)

    assert perf.actual_trading.trade_count == 3
    assert perf.actual_trading.filled_count == 2
    assert perf.actual_trading.total_pnl_amount == Decimal("500")
    assert perf.actual_trading.win_trade_count == 1
    assert perf.actual_trading.loss_trade_count == 1


async def test_actual_trading_pending_not_in_filled(db_session: AsyncSession) -> None:
    """PENDING 상태 체결은 filled_count에 포함되지 않는다."""
    strat, ver = await _add_strategy_version(db_session)
    acct = await _add_account(db_session)
    await _add_trade(db_session, acct.id, ver.id, pnl_amount=Decimal("200"), status=OrderStatus.PENDING)

    svc = StrategyPerformanceService(db_session)
    perf = await svc.get_version_performance(strat.id, ver.id)

    assert perf.actual_trading.trade_count == 1
    assert perf.actual_trading.filled_count == 0
    assert perf.actual_trading.total_pnl_amount is None


# ---------------------------------------------------------------------------
# 9. API 테스트
# ---------------------------------------------------------------------------


async def test_api_version_not_found(db_session: AsyncSession) -> None:
    """존재하지 않는 version → 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/strategies/999/versions/999/performance")
    assert resp.status_code == 404


async def test_api_empty_performance(db_session: AsyncSession) -> None:
    """신호 없는 전략 버전 → 200 + 빈 집계."""
    strat, ver = await _add_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/strategies/{strat.id}/versions/{ver.id}/performance")

    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy_id"] == strat.id
    assert data["strategy_version_id"] == ver.id
    assert data["total_signals"] == 0
    assert data["analyzed_signals"] == 0
    assert data["by_signal_type"] == []
    assert data["by_symbol"] == []
    assert data["actual_trading"]["trade_count"] == 0
    assert len(data["by_horizon"]) == 4  # HORIZONS = [5, 15, 30, 60]


async def test_api_with_signals_and_data(db_session: AsyncSession) -> None:
    """신호 + market_data가 있을 때 집계 결과가 반환된다."""
    strat, ver = await _add_strategy_version(db_session)

    # BUY 신호: entry=100, 5분 후 +10%
    await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(10))
    db_session.add(_candle(db_session, minute=11, open_=100, close=100))
    db_session.add(_candle(db_session, minute=15, close=110))
    await db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/strategies/{strat.id}/versions/{ver.id}/performance")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_signals"] == 1
    assert data["analyzed_signals"] == 1
    assert data["skipped_signals"] == 0

    h5 = next(h for h in data["by_horizon"] if h["horizon_minutes"] == 5)
    assert h5["count"] == 1
    assert h5["win_rate"] == "1.0000"
    assert h5["avg_directional_return_pct"] == "10.0000"

    buy_stat = next(s for s in data["by_signal_type"] if s["signal_type"] == "buy")
    assert buy_stat["signal_count"] == 1
    assert buy_stat["win_rate_5m"] == "1.0000"


async def test_api_wrong_strategy_version_combo(db_session: AsyncSession) -> None:
    """version_id가 다른 strategy에 속하면 404."""
    strat_a, ver_a = await _add_strategy_version(db_session)
    strat_b = Strategy(name="other", description="")
    db_session.add(strat_b)
    await db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/strategies/{strat_b.id}/versions/{ver_a.id}/performance")

    assert resp.status_code == 404
