"""PAPER-RESUME-4B — dormant limited single-symbol candidate 생성 테스트.

dormant 보장: DRAFT(스케줄러 list_active 대상 아님) + auto_trade_enabled=false +
universe_auto_trade=false + universe key 없음. 거래 side-effect 없음.
"""
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.signal_log import SignalLog
from app.domain.models.trade import Trade
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.limited_paper_candidate import (
    LimitedCandidateDuplicateError,
    LimitedCandidateValidationError,
    create_dormant_limited_candidate,
)


def _params(**over) -> dict:
    p = dict(
        strategy_type="moving_average_cross",
        symbol_code="005930",
        market="KR",
        account_id=230,
        quantity=1,
        short_window=5,
        long_window=20,
        stop_loss_pct=1.0,
        take_profit_pct=1.5,
        max_orders_per_run=1,
        auto_trade_enabled=False,
        universe_auto_trade=False,
    )
    p.update(over)
    return p


async def _create(session, name="limited-paper-005930-moving-average-cross", **over):
    return await create_dormant_limited_candidate(
        session, name=name,
        description="Limited single-symbol KR paper candidate (test)",
        parameters=_params(**over))


# --- Test 1: creates draft limited single-symbol candidate -------------------
async def test_creates_draft_limited_single_symbol_candidate(db_session: AsyncSession) -> None:
    strategy, version = await _create(db_session)
    assert strategy.id is not None
    assert version.id is not None
    assert version.status == StrategyVersionStatus.DRAFT
    assert version.parameters["symbol_code"] == "005930"
    assert version.parameters["market"] == "KR"
    assert version.parameters["account_id"] == 230
    assert "universe" not in version.parameters


# --- Test 2: candidate is dormant (not in scheduler active/testing list) -----
async def test_candidate_is_dormant_by_default(db_session: AsyncSession) -> None:
    _, version = await _create(db_session)
    assert version.parameters["auto_trade_enabled"] is False
    assert version.parameters["universe_auto_trade"] is False

    # 스케줄러는 list_active()(active/testing)만 실행 — DRAFT는 포함되지 않는다.
    active = await StrategyVersionRepository(db_session).list_active()
    assert version.id not in {v.id for v in active}


# --- Test 3: no trading side effects -----------------------------------------
async def test_candidate_creates_no_trading_side_effects(db_session: AsyncSession) -> None:
    async def c(model):
        return (await db_session.execute(select(func.count()).select_from(model))).scalar_one()
    trades_before, signals_before = await c(Trade), await c(SignalLog)

    await _create(db_session)

    assert await c(Trade) == trades_before
    assert await c(SignalLog) == signals_before


# --- Test 4: duplicate candidate protection ----------------------------------
async def test_duplicate_candidate_rejected(db_session: AsyncSession) -> None:
    await _create(db_session, name="limited-paper-dup")
    with pytest.raises(LimitedCandidateDuplicateError):
        await _create(db_session, name="limited-paper-dup")


# --- safety: validation rejects unsafe params --------------------------------
@pytest.mark.parametrize("over,msg", [
    ({"auto_trade_enabled": True}, "auto_trade_enabled"),
    ({"universe_auto_trade": True}, "universe_auto_trade"),
    ({"universe": "watchlist"}, "universe"),
    ({"market": "US"}, "market"),
    ({"symbol_code": ""}, "symbol_code"),
    ({"strategy_type": "unknown_type"}, "registry"),
])
async def test_validation_rejects_unsafe_params(db_session: AsyncSession, over, msg) -> None:
    with pytest.raises(LimitedCandidateValidationError) as e:
        await _create(db_session, name="limited-paper-reject", **over)
    assert msg in str(e.value)


# --- safety: forces flags false even if omitted ------------------------------
async def test_forces_safety_flags_false(db_session: AsyncSession) -> None:
    p = _params()
    del p["auto_trade_enabled"]
    del p["universe_auto_trade"]
    _, version = await create_dormant_limited_candidate(
        db_session, name="limited-paper-forced",
        description="x", parameters=p)
    assert version.parameters["auto_trade_enabled"] is False
    assert version.parameters["universe_auto_trade"] is False
