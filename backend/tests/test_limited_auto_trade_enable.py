"""PAPER-RESUME-4D — limited single-symbol auto-trade enable 테스트.

parameters.auto_trade_enabled false→true(단, TESTING·single-symbol·KR·paper·non-universe만).
status/그 외 필드 미변경. broad universe/live/ACTIVE/DRAFT는 거부.
"""
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, StrategyVersionStatus
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade
from app.services.limited_paper_candidate import (
    LimitedAutoTradeEnableError,
    enable_limited_auto_trade,
)


async def _account(session, account_type=AccountType.PAPER) -> Account:
    acc = Account(account_type=account_type, broker_account_no="00000000-01")
    session.add(acc)
    await session.flush()
    return acc


async def _version(session, account_id, *, status=StrategyVersionStatus.TESTING,
                   symbol="005930", market="KR", universe=False, universe_auto_trade=False,
                   auto_trade_enabled=False):
    s = Strategy(name=f"v-{account_id}-{status.value}-{symbol}-{universe}")
    session.add(s)
    await session.flush()
    params = {"strategy_type": "moving_average_cross", "market": market, "account_id": account_id,
              "quantity": 1, "max_orders_per_run": 1, "stop_loss_pct": 1.0, "take_profit_pct": 1.5,
              "auto_trade_enabled": auto_trade_enabled, "universe_auto_trade": universe_auto_trade}
    if symbol:
        params["symbol_code"] = symbol
    if universe:
        params["universe"] = "watchlist"
    v = StrategyVersion(strategy_id=s.id, version_no=1, parameters=params, status=status)
    session.add(v)
    await session.flush()
    return s, v


# --- Test 1: enables v329-like limited candidate -----------------------------
async def test_enables_limited_single_symbol_candidate(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id)
    updated = await enable_limited_auto_trade(db_session, strategy_id=s.id, version_id=v.id)
    assert updated.parameters["auto_trade_enabled"] is True
    assert updated.status == StrategyVersionStatus.TESTING          # status 미변경
    assert updated.parameters["universe_auto_trade"] is False
    assert "universe" not in updated.parameters
    assert updated.parameters["symbol_code"] == "005930"
    assert updated.parameters["quantity"] == 1
    assert updated.parameters["max_orders_per_run"] == 1


# --- Test 2: refuses broad universe candidate --------------------------------
async def test_refuses_universe_key(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id, universe=True, symbol=None)
    with pytest.raises(LimitedAutoTradeEnableError) as e:
        await enable_limited_auto_trade(db_session, strategy_id=s.id, version_id=v.id)
    assert "universe" in str(e.value)


async def test_refuses_universe_auto_trade_true(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id, universe_auto_trade=True)
    with pytest.raises(LimitedAutoTradeEnableError):
        await enable_limited_auto_trade(db_session, strategy_id=s.id, version_id=v.id)


# --- Test 3: refuses wrong status --------------------------------------------
@pytest.mark.parametrize("status", [StrategyVersionStatus.DRAFT, StrategyVersionStatus.ACTIVE])
async def test_refuses_non_testing_status(db_session: AsyncSession, status) -> None:
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id, status=status)
    with pytest.raises(LimitedAutoTradeEnableError) as e:
        await enable_limited_auto_trade(db_session, strategy_id=s.id, version_id=v.id)
    assert "TESTING" in str(e.value)


# --- refuses live account ----------------------------------------------------
async def test_refuses_live_account(db_session: AsyncSession) -> None:
    acc = await _account(db_session, account_type=AccountType.LIVE)
    s, v = await _version(db_session, acc.id)
    with pytest.raises(LimitedAutoTradeEnableError) as e:
        await enable_limited_auto_trade(db_session, strategy_id=s.id, version_id=v.id)
    assert "paper" in str(e.value)


async def test_refuses_already_enabled(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id, auto_trade_enabled=True)
    with pytest.raises(LimitedAutoTradeEnableError):
        await enable_limited_auto_trade(db_session, strategy_id=s.id, version_id=v.id)


# --- Test 4: preserves safety fields -----------------------------------------
async def test_preserves_safety_fields(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id)
    before = dict(v.parameters)
    updated = await enable_limited_auto_trade(db_session, strategy_id=s.id, version_id=v.id)
    for k in ("symbol_code", "market", "account_id", "quantity", "max_orders_per_run",
              "stop_loss_pct", "take_profit_pct", "universe_auto_trade"):
        assert updated.parameters[k] == before[k]
    assert updated.status == StrategyVersionStatus.TESTING


# --- Test 5: helper itself creates no trading side effects -------------------
async def test_enable_helper_no_trade_side_effects(db_session: AsyncSession) -> None:
    async def c(model):
        return (await db_session.execute(select(func.count()).select_from(model))).scalar_one()
    trades_before, signals_before = await c(Trade), await c(SignalLog)
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id)
    await enable_limited_auto_trade(db_session, strategy_id=s.id, version_id=v.id)
    assert await c(Trade) == trades_before
    assert await c(SignalLog) == signals_before
