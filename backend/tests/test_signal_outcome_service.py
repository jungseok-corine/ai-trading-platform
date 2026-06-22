"""Signal Outcome Analysis (Phase C-0) 통합 테스트."""
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import TradeSide
from app.domain.models.market_data import MarketData
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.main import app
from app.services.signal_outcome_service import SignalOutcomeService

KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ts(minute: int, base_date: str = "20260610", hour: int = 9) -> datetime:
    """KST datetime at given hour:minute:00."""
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


async def _add_strategy(session: AsyncSession) -> StrategyVersion:
    strat = Strategy(name="test", description="test")
    session.add(strat)
    await session.flush()
    ver = StrategyVersion(
        strategy_id=strat.id,
        version_no=1,
        parameters={"strategy_type": "moving_average_cross", "symbol_code": "005930"},
    )
    session.add(ver)
    await session.flush()
    return ver


async def _add_signal(
    session: AsyncSession,
    version_id: int,
    signal_type: TradeSide = TradeSide.BUY,
    candle_ts: datetime | None = None,
    symbol: str = "005930",
) -> SignalLog:
    log = SignalLog(
        symbol_code=symbol,
        strategy_version_id=version_id,
        signal_type=signal_type,
        generated_at=datetime.now(KST),
        candle_ts=candle_ts or _ts(30),  # default: 09:30
    )
    session.add(log)
    await session.flush()
    return log


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _db_override(db_session: AsyncSession):
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    yield
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 1. BUY 신호 수익률 계산
# ---------------------------------------------------------------------------


async def test_buy_signal_returns_across_horizons(db_session: AsyncSession) -> None:
    """BUY 신호 이후 5/15/30/60분 수익률이 올바르게 계산된다."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(30))

    # 09:30: 신호 캔들 (before ref_ts, market_data에는 있지만 outcome 계산에는 안 씀)
    # 09:31: 진입 캔들 (entry_price = open = 100)
    # 09:35: 5분 horizon close = 110 → return = +10%
    # 09:45: 15분 horizon close = 90  → return = -10%
    # 10:00: 30분 horizon close = 120 → return = +20%
    # 10:30: 60분 horizon close = 150 → return = +50%
    candles = [
        _candle(db_session, minute=31, open_=100, high=105, low=95,  close=103),        # entry
        _candle(db_session, minute=35, open_=103, high=115, low=100, close=110),        # 5m
        _candle(db_session, minute=45, open_=110, high=110, low=85,  close=90),         # 15m
        _candle(db_session, hour=10,  minute=0,  open_=90,  high=125, low=88, close=120),  # 30m (10:00)
    ]
    # 60분 horizon: 10:30
    candles.append(_candle(db_session, minute=30, hour=10, open_=120, high=155, low=115, close=150))
    for c in candles:
        db_session.add(c)
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    assert outcome is not None
    assert outcome.available is True
    assert outcome.entry_price == Decimal("100")

    hr = {h.horizon_minutes: h for h in outcome.horizons}
    assert hr[5].available is True
    assert hr[5].return_pct == Decimal("10.0000")

    assert hr[15].available is True
    assert hr[15].return_pct == Decimal("-10.0000")

    assert hr[30].available is True
    assert hr[30].return_pct == Decimal("20.0000")

    assert hr[60].available is True
    assert hr[60].return_pct == Decimal("50.0000")


async def test_outcome_uses_signal_timeframe_not_hardcoded_1m(db_session: AsyncSession) -> None:
    """5m 신호(미장 등)는 5m market_data로 결과를 계산한다(이전엔 1m 고정이라 미조회)."""
    ver = await _add_strategy(db_session)
    sig = SignalLog(
        symbol_code="AAPL", market="US", timeframe="5m",
        strategy_version_id=ver.id, signal_type=TradeSide.BUY,
        generated_at=datetime.now(KST), candle_ts=_ts(30),
    )
    db_session.add(sig)
    await db_session.flush()

    # 5m 시세: 진입(09:35 open=100) → 5분(09:40 close=110)
    db_session.add(_candle(db_session, symbol="AAPL", tf="5m", minute=35, open_=100, close=103))
    db_session.add(_candle(db_session, symbol="AAPL", tf="5m", minute=40, open_=103, close=110))
    # 1m 시세(엉뚱한 값) — timeframe이 달라 결과 계산에 쓰이면 안 된다.
    db_session.add(_candle(db_session, symbol="AAPL", tf="1m", minute=35, open_=999, close=999))
    await db_session.flush()

    outcome = await SignalOutcomeService(db_session).get_outcome(sig.id)

    assert outcome is not None
    assert outcome.available is True       # 1m 고정이었으면 'no market_data' 였을 것
    assert outcome.timeframe == "5m"
    assert outcome.entry_price == Decimal("100")  # 5m 진입가(1m 999 아님)


# ---------------------------------------------------------------------------
# 2. market_data 부족 → unavailable
# ---------------------------------------------------------------------------


async def test_no_market_data_returns_unavailable(db_session: AsyncSession) -> None:
    """신호 이후 market_data가 없으면 available=False로 반환한다 (예외 없음)."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(30))
    # market_data 없음

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    assert outcome.available is False
    assert outcome.entry_price is None
    assert outcome.note is not None
    assert all(not h.available for h in outcome.horizons)


async def test_partial_market_data_some_horizons_unavailable(db_session: AsyncSession) -> None:
    """일부 horizon 데이터만 있어도 있는 것은 계산하고 없는 것은 available=False."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(30))

    # 09:31 (entry)와 09:35 (5분)만 존재; 15분/30분/60분 없음
    db_session.add(_candle(db_session, minute=31, open_=100, close=100))
    db_session.add(_candle(db_session, minute=35, close=110))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    assert outcome.available is True
    hr = {h.horizon_minutes: h for h in outcome.horizons}
    assert hr[5].available is True
    assert hr[15].available is False
    assert hr[30].available is False
    assert hr[60].available is False


# ---------------------------------------------------------------------------
# 3. SELL 신호
# ---------------------------------------------------------------------------


async def test_sell_signal_return_direction(db_session: AsyncSession) -> None:
    """SELL 신호 이후 가격이 하락하면 return_pct < 0 (신호가 맞은 것)."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.SELL, candle_ts=_ts(30))

    # entry 100, 5분 후 close 80 → return = -20%
    db_session.add(_candle(db_session, minute=31, open_=100, close=100))
    db_session.add(_candle(db_session, minute=35, close=80))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    assert outcome.available is True
    hr = {h.horizon_minutes: h for h in outcome.horizons}
    assert hr[5].return_pct == Decimal("-20.0000")


async def test_sell_signal_price_rises_gives_positive_return(db_session: AsyncSession) -> None:
    """SELL 신호 이후 가격이 상승하면 return_pct > 0 (신호가 틀린 것, 방향 해석은 호출자 책임)."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.SELL, candle_ts=_ts(30))

    db_session.add(_candle(db_session, minute=31, open_=100, close=100))
    db_session.add(_candle(db_session, minute=35, close=120))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    hr = {h.horizon_minutes: h for h in outcome.horizons}
    assert hr[5].return_pct == Decimal("20.0000")


# ---------------------------------------------------------------------------
# 4. MFE/MAE 계산
# ---------------------------------------------------------------------------


async def test_buy_mfe_mae(db_session: AsyncSession) -> None:
    """BUY: MFE = 최고가-진입가, MAE = 진입가-최저가 (entry 기준)."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(30))

    # entry=100, high 최대=130, low 최소=80
    db_session.add(_candle(db_session, minute=31, open_=100, high=110, low=95, close=105))
    db_session.add(_candle(db_session, minute=35, high=130, low=80, close=100))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    assert outcome.mfe_pct is not None
    assert outcome.mae_pct is not None
    # MFE = (130 - 100) / 100 * 100 = 30%
    assert outcome.mfe_pct == Decimal("30.0000")
    # MAE = (100 - 80) / 100 * 100 = 20%
    assert outcome.mae_pct == Decimal("20.0000")


async def test_sell_mfe_mae(db_session: AsyncSession) -> None:
    """SELL: MFE = 진입가-최저가 (가격 하락 = 유리), MAE = 최고가-진입가 (가격 상승 = 불리)."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.SELL, candle_ts=_ts(30))

    # entry=100, high 최대=120, low 최소=70
    db_session.add(_candle(db_session, minute=31, open_=100, high=105, low=95, close=100))
    db_session.add(_candle(db_session, minute=35, high=120, low=70, close=85))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    # SELL MFE = (100 - 70) / 100 * 100 = 30%
    assert outcome.mfe_pct == Decimal("30.0000")
    # SELL MAE = (120 - 100) / 100 * 100 = 20%
    assert outcome.mae_pct == Decimal("20.0000")


# ---------------------------------------------------------------------------
# 5. 존재하지 않는 신호
# ---------------------------------------------------------------------------


async def test_get_outcome_nonexistent_signal_returns_none(db_session: AsyncSession) -> None:
    svc = SignalOutcomeService(db_session)
    result = await svc.get_outcome(99999)
    assert result is None


# ---------------------------------------------------------------------------
# 6. summary API
# ---------------------------------------------------------------------------


async def test_summary_empty_db(db_session: AsyncSession) -> None:
    """신호가 없으면 빈 summary가 반환된다."""
    svc = SignalOutcomeService(db_session)
    summary = await svc.get_summary()

    assert summary.total_signals == 0
    assert summary.analyzed_count == 0
    assert summary.skipped_count == 0
    assert summary.by_symbol == []
    assert summary.by_signal_type == []


async def test_summary_counts_analyzed_and_skipped(db_session: AsyncSession) -> None:
    """market_data 있는 신호는 analyzed, 없는 신호는 skipped로 집계된다."""
    ver = await _add_strategy(db_session)

    # 신호 A: market_data 있음
    sig_a = await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(30))
    db_session.add(_candle(db_session, minute=31, open_=100, close=105))
    await db_session.flush()

    # 신호 B: market_data 없음
    await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(40))

    svc = SignalOutcomeService(db_session)
    summary = await svc.get_summary()

    assert summary.total_signals == 2
    assert summary.analyzed_count == 1
    assert summary.skipped_count == 1


async def test_summary_win_rate_buy(db_session: AsyncSession) -> None:
    """BUY 신호 2개 중 1개가 5분 후 상승 → win_rate = 0.5."""
    ver = await _add_strategy(db_session)

    # 신호 1: 5분 후 +5% (win)
    await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(10))
    db_session.add(_candle(db_session, minute=11, open_=100, close=100))
    db_session.add(_candle(db_session, minute=15, close=105))

    # 신호 2: 5분 후 -5% (loss)
    await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(20))
    db_session.add(_candle(db_session, minute=21, open_=100, close=100))
    db_session.add(_candle(db_session, minute=25, close=95))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    summary = await svc.get_summary()

    h5 = next(h for h in summary.by_horizon if h.horizon_minutes == 5)
    assert h5.count == 2
    assert h5.win_rate == Decimal("0.5000")


async def test_summary_filter_by_signal_type(db_session: AsyncSession) -> None:
    """signal_type=buy 필터 적용 시 SELL 신호는 집계에서 제외된다."""
    ver = await _add_strategy(db_session)
    await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(10))
    await _add_signal(db_session, ver.id, TradeSide.SELL, candle_ts=_ts(20))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    summary = await svc.get_summary(signal_type=TradeSide.BUY)

    assert summary.total_signals == 1


async def test_summary_filter_by_symbol(db_session: AsyncSession) -> None:
    """symbol_code 필터 적용 시 다른 종목 신호는 제외된다."""
    ver = await _add_strategy(db_session)
    await _add_signal(db_session, ver.id, symbol="005930", candle_ts=_ts(10))
    await _add_signal(db_session, ver.id, symbol="035420", candle_ts=_ts(20))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    summary = await svc.get_summary(symbol_code="005930")

    assert summary.total_signals == 1


async def test_summary_by_symbol_groups_correctly(db_session: AsyncSession) -> None:
    """by_symbol 집계가 종목별로 올바르게 분리된다."""
    ver = await _add_strategy(db_session)

    # 005930 신호: market_data 있음
    await _add_signal(db_session, ver.id, symbol="005930", candle_ts=_ts(10))
    db_session.add(_candle(db_session, symbol="005930", minute=11, open_=100, close=105))

    # 035420 신호: market_data 없음
    await _add_signal(db_session, ver.id, symbol="035420", candle_ts=_ts(10))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    summary = await svc.get_summary()

    syms = {s.symbol_code: s for s in summary.by_symbol}
    assert "005930" in syms
    assert syms["005930"].analyzed_count == 1


# ---------------------------------------------------------------------------
# 7. API 엔드포인트 통합 테스트
# ---------------------------------------------------------------------------


async def test_api_get_signal_outcome_not_found(db_session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/signals/99999/outcome")
    assert resp.status_code == 404


async def test_api_get_signal_outcome_no_market_data(db_session: AsyncSession) -> None:
    """market_data 없어도 200 + available=False 반환 (404 아님)."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(30))
    await db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/signals/{sig.id}/outcome")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["entry_price"] is None
    assert all(not h["available"] for h in data["horizons"])


async def test_api_get_signal_outcome_with_data(db_session: AsyncSession) -> None:
    """market_data가 있으면 수익률이 계산된 결과를 반환한다."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(30))
    db_session.add(_candle(db_session, minute=31, open_=100, close=100))
    db_session.add(_candle(db_session, minute=35, close=110))
    await db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/signals/{sig.id}/outcome")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["entry_price"] == "100.0000"
    assert data["signal_type"] == "buy"
    h5 = next(h for h in data["horizons"] if h["horizon_minutes"] == 5)
    assert h5["available"] is True
    assert h5["return_pct"] == "10.0000"


async def test_api_outcomes_summary_empty(db_session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/signals/outcomes/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_signals"] == 0
    assert data["analyzed_count"] == 0
    assert data["skipped_count"] == 0


async def test_api_outcomes_summary_routing_not_captured_by_signal_id(db_session: AsyncSession) -> None:
    """/signals/outcomes/summary 가 /{signal_id} 라우트에 가로채이지 않는다."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/signals/outcomes/summary")

    assert resp.status_code == 200
    assert "total_signals" in resp.json()


async def test_api_outcomes_summary_with_data(db_session: AsyncSession) -> None:
    """신호와 market_data가 있을 때 summary API가 집계 결과를 반환한다."""
    ver = await _add_strategy(db_session)
    await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(10))
    db_session.add(_candle(db_session, minute=11, open_=100, close=100))
    db_session.add(_candle(db_session, minute=15, close=110))
    await db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/signals/outcomes/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["analyzed_count"] == 1
    h5 = next(h for h in data["by_horizon"] if h["horizon_minutes"] == 5)
    assert h5["count"] == 1
    assert h5["win_rate"] == "1.0000"  # 1개 중 1개 win


async def test_api_outcomes_summary_limit_param(db_session: AsyncSession) -> None:
    """limit 파라미터가 동작한다."""
    ver = await _add_strategy(db_session)
    for i in range(5):
        await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(i))
    await db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/signals/outcomes/summary", params={"limit": 2})

    assert resp.status_code == 200
    assert resp.json()["total_signals"] == 2


async def test_api_outcomes_summary_max_limit_enforced(db_session: AsyncSession) -> None:
    """limit > 500 이면 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/signals/outcomes/summary", params={"limit": 9999})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 8. 방향성 필드 (is_win, directional_return_pct) — C-0.1
# ---------------------------------------------------------------------------


async def test_buy_win_directional_fields(db_session: AsyncSession) -> None:
    """BUY 신호 이후 가격 상승 → is_win=True, directional_return_pct > 0."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(30))
    # entry=100, 5분 후 close=110 → return_pct=+10%
    db_session.add(_candle(db_session, minute=31, open_=100, close=100))
    db_session.add(_candle(db_session, minute=35, close=110))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    h5 = next(h for h in outcome.horizons if h.horizon_minutes == 5)
    assert h5.available is True
    assert h5.is_win is True
    assert h5.directional_return_pct is not None
    assert h5.directional_return_pct > 0
    assert h5.directional_return_pct == h5.return_pct  # BUY: 동일해야 함


async def test_buy_loss_directional_fields(db_session: AsyncSession) -> None:
    """BUY 신호 이후 가격 하락 → is_win=False, directional_return_pct < 0."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(30))
    # entry=100, 5분 후 close=90 → return_pct=-10%
    db_session.add(_candle(db_session, minute=31, open_=100, close=100))
    db_session.add(_candle(db_session, minute=35, close=90))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    h5 = next(h for h in outcome.horizons if h.horizon_minutes == 5)
    assert h5.is_win is False
    assert h5.directional_return_pct is not None
    assert h5.directional_return_pct < 0
    assert h5.return_pct == Decimal("-10.0000")
    assert h5.directional_return_pct == Decimal("-10.0000")


async def test_sell_win_directional_fields(db_session: AsyncSession) -> None:
    """SELL 신호 이후 가격 하락 → return_pct 음수지만 directional_return_pct 양수, is_win=True."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.SELL, candle_ts=_ts(30))
    # entry=100, 5분 후 close=80 → return_pct=-20%, directional_return_pct=+20%
    db_session.add(_candle(db_session, minute=31, open_=100, close=100))
    db_session.add(_candle(db_session, minute=35, close=80))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    h5 = next(h for h in outcome.horizons if h.horizon_minutes == 5)
    assert h5.available is True
    assert h5.return_pct == Decimal("-20.0000")        # raw: 가격 하락
    assert h5.directional_return_pct == Decimal("20.0000")  # SELL: -return_pct
    assert h5.is_win is True


async def test_sell_loss_directional_fields(db_session: AsyncSession) -> None:
    """SELL 신호 이후 가격 상승 → return_pct 양수지만 directional_return_pct 음수, is_win=False."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.SELL, candle_ts=_ts(30))
    # entry=100, 5분 후 close=120 → return_pct=+20%, directional_return_pct=-20%
    db_session.add(_candle(db_session, minute=31, open_=100, close=100))
    db_session.add(_candle(db_session, minute=35, close=120))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    h5 = next(h for h in outcome.horizons if h.horizon_minutes == 5)
    assert h5.available is True
    assert h5.return_pct == Decimal("20.0000")          # raw: 가격 상승
    assert h5.directional_return_pct == Decimal("-20.0000")  # SELL: -return_pct
    assert h5.is_win is False


async def test_unavailable_horizon_directional_fields_are_null(db_session: AsyncSession) -> None:
    """데이터 없는 horizon의 is_win과 directional_return_pct는 None이다."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(30))
    # entry 캔들만 있고 5분 이후 없음
    db_session.add(_candle(db_session, minute=31, open_=100, close=100))
    await db_session.flush()

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    for h in outcome.horizons:
        if not h.available:
            assert h.is_win is None
            assert h.directional_return_pct is None


async def test_unavailable_outcome_all_directional_fields_are_null(db_session: AsyncSession) -> None:
    """market_data 없어서 available=False인 경우 모든 horizon의 is_win, directional_return_pct가 None."""
    ver = await _add_strategy(db_session)
    sig = await _add_signal(db_session, ver.id, TradeSide.BUY, candle_ts=_ts(30))
    # market_data 없음

    svc = SignalOutcomeService(db_session)
    outcome = await svc.get_outcome(sig.id)

    assert outcome.available is False
    assert all(h.is_win is None for h in outcome.horizons)
    assert all(h.directional_return_pct is None for h in outcome.horizons)
