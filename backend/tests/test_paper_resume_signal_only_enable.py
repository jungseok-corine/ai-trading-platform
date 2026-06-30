"""PAPER-RESUME-4C — dormant candidate를 signal-only TESTING으로 전환 테스트.

status DRAFT→TESTING(컬럼)만 변경. auto_trade_enabled/universe_auto_trade/universe는 미변경·가드.
TESTING이라 scheduler 대상이 되지만 auto_trade_enabled=false라 주문 시도 대상은 아님.
"""
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.trade import Trade
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.limited_paper_candidate import (
    SignalOnlyEnableError,
    create_dormant_limited_candidate,
    enable_signal_only_testing,
)


def _params(**over) -> dict:
    p = dict(
        strategy_type="moving_average_cross", symbol_code="005930", market="KR",
        account_id=230, quantity=1, short_window=5, long_window=20,
        stop_loss_pct=1.0, take_profit_pct=1.5, max_orders_per_run=1,
        auto_trade_enabled=False, universe_auto_trade=False)
    p.update(over)
    return p


async def _candidate(session, name="limited-paper-005930-mac", **over):
    return await create_dormant_limited_candidate(
        session, name=name, description="signal-only test", parameters=_params(**over))


# --- Test 1: DRAFT -> signal-only TESTING ------------------------------------
async def test_transition_dormant_to_signal_only_testing(db_session: AsyncSession) -> None:
    strategy, version = await _candidate(db_session)
    assert version.status == StrategyVersionStatus.DRAFT

    updated = await enable_signal_only_testing(
        db_session, strategy_id=strategy.id, version_id=version.id)

    assert updated.status == StrategyVersionStatus.TESTING
    assert updated.parameters["auto_trade_enabled"] is False
    assert updated.parameters["universe_auto_trade"] is False
    assert "universe" not in updated.parameters


# --- Test 2: signal-only is scheduler-visible but order-disabled --------------
async def test_signal_only_scheduler_visible_but_order_disabled(db_session: AsyncSession) -> None:
    strategy, version = await _candidate(db_session)
    await enable_signal_only_testing(db_session, strategy_id=strategy.id, version_id=version.id)

    active = await StrategyVersionRepository(db_session).list_active()  # active/testing
    assert version.id in {v.id for v in active}  # scheduler 대상

    # auto_trade_enabled=false → 주문 시도 조건 불충족(런너는 신호만 로깅).
    refreshed = await StrategyVersionRepository(db_session).get(version.id)
    assert refreshed.parameters["auto_trade_enabled"] is False


# --- Test 3: no risk/order/trade mutation ------------------------------------
async def test_signal_only_enable_no_trade_side_effects(db_session: AsyncSession) -> None:
    trades_before = (await db_session.execute(select(func.count()).select_from(Trade))).scalar_one()
    strategy, version = await _candidate(db_session)
    await enable_signal_only_testing(db_session, strategy_id=strategy.id, version_id=version.id)
    assert (await db_session.execute(select(func.count()).select_from(Trade))).scalar_one() == trades_before


# --- Test 4: unsafe transitions guarded --------------------------------------
async def test_rejects_when_auto_trade_enabled_true(db_session: AsyncSession) -> None:
    # create helper forces false, so build a DRAFT then manually set param to true to test guard.
    strategy, version = await _candidate(db_session, name="limited-paper-guard1")
    version.parameters = {**version.parameters, "auto_trade_enabled": True}
    await db_session.flush()
    with pytest.raises(SignalOnlyEnableError) as e:
        await enable_signal_only_testing(db_session, strategy_id=strategy.id, version_id=version.id)
    assert "auto_trade_enabled" in str(e.value)


async def test_rejects_when_universe_key_present(db_session: AsyncSession) -> None:
    strategy, version = await _candidate(db_session, name="limited-paper-guard2")
    version.parameters = {**version.parameters, "universe": "watchlist"}
    await db_session.flush()
    with pytest.raises(SignalOnlyEnableError) as e:
        await enable_signal_only_testing(db_session, strategy_id=strategy.id, version_id=version.id)
    assert "universe" in str(e.value)


async def test_rejects_when_not_draft(db_session: AsyncSession) -> None:
    strategy, version = await _candidate(db_session, name="limited-paper-guard3")
    await enable_signal_only_testing(db_session, strategy_id=strategy.id, version_id=version.id)
    # 이미 TESTING → 재전환 거부.
    with pytest.raises(SignalOnlyEnableError) as e:
        await enable_signal_only_testing(db_session, strategy_id=strategy.id, version_id=version.id)
    assert "DRAFT" in str(e.value)
