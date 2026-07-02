"""C-6.13: 백테스트 예측 적중률 — 백테스트 verdict vs 회고 판정 일치도."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ProposalStatus, StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.strategy_proposal import StrategyProposal
from app.services.proposal_retrospective_service import ProposalRetrospectiveService


async def _approved_proposal(
    session: AsyncSession, bt_verdict: str | None
) -> StrategyProposal:
    strategy = Strategy(name="acc test", description="t")
    session.add(strategy)
    await session.flush()
    base = StrategyVersion(
        strategy_id=strategy.id, version_no=1, parameters={},
        status=StrategyVersionStatus.TESTING,
    )
    new = StrategyVersion(
        strategy_id=strategy.id, version_no=2, parameters={},
        status=StrategyVersionStatus.TESTING,
    )
    session.add_all([base, new])
    await session.flush()
    p = StrategyProposal(
        strategy_id=strategy.id,
        base_version_id=base.id,
        created_version_id=new.id,
        title="acc",
        suggested_parameters={"strategy_type": "moving_average_cross"},
        status=ProposalStatus.APPROVED,
        backtest_summary={"verdict": bt_verdict} if bt_verdict else None,
    )
    session.add(p)
    await session.commit()
    return p


def _fake_expectancy(base_val: float, new_val: float):
    """base/new 버전의 기대값을 순서대로 돌려주는 mock (표본 충분 가정)."""
    values = iter([(base_val, 100), (new_val, 100)])

    async def _impl(self, version_id):
        return next(values)

    return _impl


@pytest.mark.asyncio
async def test_hit_when_backtest_and_retro_agree(db_session: AsyncSession):
    await _approved_proposal(db_session, "proposed_better")
    svc = ProposalRetrospectiveService(db_session)
    # 회고: 새 버전이 실제로 개선 (base 1.0 → new 2.0)
    with patch.object(
        ProposalRetrospectiveService, "_strategy_expectancy", _fake_expectancy(1.0, 2.0)
    ):
        acc = await svc.backtest_accuracy()
    assert acc["comparable"] == 1
    assert acc["hits"] == 1 and acc["misses"] == 0
    assert acc["hit_rate"] == 1.0


@pytest.mark.asyncio
async def test_miss_when_backtest_and_retro_disagree(db_session: AsyncSession):
    await _approved_proposal(db_session, "proposed_better")
    svc = ProposalRetrospectiveService(db_session)
    # 회고: 실제로는 악화 (base 2.0 → new 1.0)
    with patch.object(
        ProposalRetrospectiveService, "_strategy_expectancy", _fake_expectancy(2.0, 1.0)
    ):
        acc = await svc.backtest_accuracy()
    assert acc["comparable"] == 1
    assert acc["misses"] == 1
    assert acc["hit_rate"] == 0.0


@pytest.mark.asyncio
async def test_inconclusive_backtest_excluded(db_session: AsyncSession):
    await _approved_proposal(db_session, "inconclusive")
    await _approved_proposal(db_session, None)  # 백테스트 없음(옛 제안)
    acc = await ProposalRetrospectiveService(db_session).backtest_accuracy()
    assert acc["comparable"] == 0
    assert acc["hit_rate"] is None
