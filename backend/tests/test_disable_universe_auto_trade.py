"""PAPER-RESUME-UNIVERSE-OFF — broad universe auto-trade 비활성 테스트.

universe_auto_trade true→false(parameters JSONB). status 미변경. single-symbol/live는 보호.
"""
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade
from app.services.limited_paper_candidate import (
    DisableUniverseAutoTradeError,
    disable_universe_auto_trade,
)


async def _account(session, account_type=AccountType.PAPER) -> Account:
    acc = Account(account_type=account_type, broker_account_no="00000000-01")
    session.add(acc)
    await session.flush()
    return acc


async def _universe_version(session, account_id, *, universe="watchlist",
                            universe_auto_trade=True, auto_trade_enabled=False,
                            status=StrategyVersionStatus.TESTING):
    strat = Strategy(name=f"u-{account_id}-{universe}-{universe_auto_trade}")
    session.add(strat)
    await session.flush()
    params = {"strategy_type": "macd_trend", "market": "KR", "account_id": account_id,
              "universe": universe, "universe_auto_trade": universe_auto_trade,
              "auto_trade_enabled": auto_trade_enabled}
    v = StrategyVersion(strategy_id=strat.id, version_no=1, parameters=params, status=status)
    session.add(v)
    await session.flush()
    return strat, v


async def _single_symbol_version(session, account_id):
    strat = Strategy(name=f"s-{account_id}")
    session.add(strat)
    await session.flush()
    params = {"strategy_type": "moving_average_cross", "market": "KR", "account_id": account_id,
              "symbol_code": "005930", "auto_trade_enabled": False, "universe_auto_trade": False}
    v = StrategyVersion(strategy_id=strat.id, version_no=1, parameters=params,
                        status=StrategyVersionStatus.TESTING)
    session.add(v)
    await session.flush()
    return strat, v


# --- Test 1: disables broad universe auto-trade, status unchanged ------------
async def test_disables_broad_universe_auto_trade(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    strat, v = await _universe_version(db_session, acc.id, universe="watchlist")
    assert v.status == StrategyVersionStatus.TESTING

    updated = await disable_universe_auto_trade(db_session, strategy_id=strat.id, version_id=v.id)

    assert updated.parameters["universe_auto_trade"] is False
    assert "universe" in updated.parameters  # universe 자체는 유지(signal 관찰)
    assert updated.status == StrategyVersionStatus.TESTING  # status 미변경


async def test_disables_scanner_candidates_universe(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    strat, v = await _universe_version(db_session, acc.id, universe="scanner_candidates")
    updated = await disable_universe_auto_trade(db_session, strategy_id=strat.id, version_id=v.id)
    assert updated.parameters["universe_auto_trade"] is False


async def test_also_clears_auto_trade_enabled_if_true(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    strat, v = await _universe_version(db_session, acc.id, auto_trade_enabled=True)
    updated = await disable_universe_auto_trade(db_session, strategy_id=strat.id, version_id=v.id)
    assert updated.parameters["universe_auto_trade"] is False
    assert updated.parameters["auto_trade_enabled"] is False


# --- Test 2: does not modify single-symbol candidate -------------------------
async def test_refuses_single_symbol_version(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    strat, v = await _single_symbol_version(db_session, acc.id)
    with pytest.raises(DisableUniverseAutoTradeError) as e:
        await disable_universe_auto_trade(db_session, strategy_id=strat.id, version_id=v.id)
    assert "single-symbol" in str(e.value)


# --- Test 3: refuses live account --------------------------------------------
async def test_refuses_live_account(db_session: AsyncSession) -> None:
    acc = await _account(db_session, account_type=AccountType.LIVE)
    strat, v = await _universe_version(db_session, acc.id)
    with pytest.raises(DisableUniverseAutoTradeError) as e:
        await disable_universe_auto_trade(db_session, strategy_id=strat.id, version_id=v.id)
    assert "paper only" in str(e.value)


async def test_refuses_when_already_false(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    strat, v = await _universe_version(db_session, acc.id, universe_auto_trade=False)
    with pytest.raises(DisableUniverseAutoTradeError):
        await disable_universe_auto_trade(db_session, strategy_id=strat.id, version_id=v.id)


# --- Test 4: no trading side effects -----------------------------------------
async def test_no_trade_side_effects(db_session: AsyncSession) -> None:
    trades_before = (await db_session.execute(select(func.count()).select_from(Trade))).scalar_one()
    acc = await _account(db_session)
    strat, v = await _universe_version(db_session, acc.id)
    await disable_universe_auto_trade(db_session, strategy_id=strat.id, version_id=v.id)
    assert (await db_session.execute(select(func.count()).select_from(Trade))).scalar_one() == trades_before
