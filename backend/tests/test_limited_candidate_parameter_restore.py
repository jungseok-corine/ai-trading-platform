"""UI-PARAMS-FIX-1 — limited single-symbol candidate parameters 복구(sanitize) 테스트.

UI 폼 저장으로 오염된 parameters(enabled=false, timeframe='5', universe 키, 스퍼리어스 default 다수)를
의도 상태(enabled=true, timeframe='1m', universe 키 없음, allowed key set만)로 복구.
status/auto_trade_enabled=true/single-symbol 안전 필드는 유지.
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
    LimitedCandidateRestoreError,
    restore_limited_auto_trade_parameters,
)

# UI 저장으로 오염된 상태를 재현.
_POLLUTED = {
    "enabled": False, "timeframe": "5", "auto_trade_enabled": True, "universe_auto_trade": False,
    "universe": None, "universe_market": None, "universe_lookback_days": 5,
    "strategy_type": "moving_average_cross", "symbol_code": "005930", "market": "KR",
    "account_id": 230, "quantity": 1, "max_orders_per_run": 1, "short_window": 5, "long_window": 20,
    "stop_loss_pct": 1.0, "take_profit_pct": 1.5,
    # 스퍼리어스 UI default keys
    "rsi_period": 14, "fast_period": 12, "slow_period": 26, "signal_period": 9,
    "volume_window": 20, "volume_multiplier": 1.5, "surge_lookback": 5, "breakout_lookback": 20,
    "cash_amount": 0, "cash_pct": 0, "quantity_mode": "fixed", "exit_on_close": False,
    "exit_mode": "overbought", "flow_mode": "off",
}


async def _account(session, account_type=AccountType.PAPER) -> Account:
    acc = Account(account_type=account_type, broker_account_no="00000000-01")
    session.add(acc)
    await session.flush()
    return acc


async def _version(session, account_id, **param_over):
    s = Strategy(name=f"restore-{account_id}-{len(param_over)}")
    session.add(s)
    await session.flush()
    params = {**_POLLUTED, "account_id": account_id}
    params.update(param_over)
    v = StrategyVersion(strategy_id=s.id, version_no=1, parameters=params,
                        status=param_over.pop("__status", StrategyVersionStatus.TESTING)
                        if "__status" in param_over else StrategyVersionStatus.TESTING)
    session.add(v)
    await session.flush()
    return s, v


# --- Test 1: restores enabled and timeframe ----------------------------------
async def test_restores_enabled_and_timeframe(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id)
    updated = await restore_limited_auto_trade_parameters(
        db_session, strategy_id=s.id, version_id=v.id, expected_account_id=acc.id)
    assert updated.parameters["enabled"] is True
    assert updated.parameters["timeframe"] == "1m"


# --- Test 2: removes universe key --------------------------------------------
async def test_removes_universe_key(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id)
    updated = await restore_limited_auto_trade_parameters(
        db_session, strategy_id=s.id, version_id=v.id, expected_account_id=acc.id)
    assert "universe" not in updated.parameters
    assert "universe_market" not in updated.parameters
    assert updated.parameters["universe_auto_trade"] is False


# --- Test 3: preserves limited auto-trade safety fields ----------------------
async def test_preserves_safety_fields(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id)
    updated = await restore_limited_auto_trade_parameters(
        db_session, strategy_id=s.id, version_id=v.id, expected_account_id=acc.id)
    assert updated.parameters["auto_trade_enabled"] is True
    assert updated.status == StrategyVersionStatus.TESTING
    assert updated.parameters["symbol_code"] == "005930"
    assert updated.parameters["account_id"] == acc.id
    assert updated.parameters["quantity"] == 1
    assert updated.parameters["max_orders_per_run"] == 1
    assert updated.parameters["short_window"] == 5
    assert updated.parameters["long_window"] == 20
    assert updated.parameters["stop_loss_pct"] == 1.0
    assert updated.parameters["take_profit_pct"] == 1.5


# --- Test 4: removes unrelated UI default keys -------------------------------
async def test_removes_unrelated_keys(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id)
    updated = await restore_limited_auto_trade_parameters(
        db_session, strategy_id=s.id, version_id=v.id, expected_account_id=acc.id)
    for spurious in ("rsi_period", "fast_period", "slow_period", "volume_window",
                     "surge_lookback", "breakout_lookback", "cash_pct", "quantity_mode",
                     "exit_mode", "flow_mode", "universe_lookback_days"):
        assert spurious not in updated.parameters
    # allowed key set만 남음
    assert set(updated.parameters.keys()) == {
        "enabled", "strategy_type", "symbol_code", "market", "account_id", "quantity",
        "short_window", "long_window", "timeframe", "stop_loss_pct", "take_profit_pct",
        "max_orders_per_run", "auto_trade_enabled", "universe_auto_trade"}


# --- Test 5: refuses wrong candidate -----------------------------------------
async def test_refuses_wrong_symbol(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id, symbol_code="000660")
    with pytest.raises(LimitedCandidateRestoreError):
        await restore_limited_auto_trade_parameters(
            db_session, strategy_id=s.id, version_id=v.id, expected_account_id=acc.id)


async def test_refuses_non_testing(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    s = Strategy(name="restore-draft")
    db_session.add(s); await db_session.flush()
    v = StrategyVersion(strategy_id=s.id, version_no=1,
                        parameters={**_POLLUTED, "account_id": acc.id},
                        status=StrategyVersionStatus.DRAFT)
    db_session.add(v); await db_session.flush()
    with pytest.raises(LimitedCandidateRestoreError) as e:
        await restore_limited_auto_trade_parameters(
            db_session, strategy_id=s.id, version_id=v.id, expected_account_id=acc.id)
    assert "TESTING" in str(e.value)


async def test_refuses_live_account(db_session: AsyncSession) -> None:
    acc = await _account(db_session, account_type=AccountType.LIVE)
    s, v = await _version(db_session, acc.id)
    with pytest.raises(LimitedCandidateRestoreError) as e:
        await restore_limited_auto_trade_parameters(
            db_session, strategy_id=s.id, version_id=v.id, expected_account_id=acc.id)
    assert "paper" in str(e.value)


async def test_refuses_wrong_strategy_type(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id, strategy_type="rsi_reversion")
    with pytest.raises(LimitedCandidateRestoreError):
        await restore_limited_auto_trade_parameters(
            db_session, strategy_id=s.id, version_id=v.id, expected_account_id=acc.id)


# --- Test 6: helper creates no trading side effects --------------------------
async def test_restore_no_trade_side_effects(db_session: AsyncSession) -> None:
    async def c(model):
        return (await db_session.execute(select(func.count()).select_from(model))).scalar_one()
    trades_before, signals_before = await c(Trade), await c(SignalLog)
    acc = await _account(db_session)
    s, v = await _version(db_session, acc.id)
    await restore_limited_auto_trade_parameters(
        db_session, strategy_id=s.id, version_id=v.id, expected_account_id=acc.id)
    assert await c(Trade) == trades_before
    assert await c(SignalLog) == signals_before
