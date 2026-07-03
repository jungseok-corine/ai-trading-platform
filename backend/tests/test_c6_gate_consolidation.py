"""C-6.16: Paper 승인 게이트 통합 — 승인+실험준비+readiness 원클릭.

안전 검증: 생성물은 여전히 DRAFT + auto_trade=False (runner 비적격),
rejected엔 준비 없음, 플래그 없으면 기존 동작(상태만 변경) 그대로.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.services.candidate_proposal_experiment_service import (
    CandidateProposalExperimentService,
    ProposalNotApprovedError,
)
from app.services.candidate_strategy_proposal_service import (
    CandidateStrategyProposalService,
)
from tests.test_candidate_strategy_proposal import _seed_candidate


async def _pending_proposal(session: AsyncSession):
    candidate = await _seed_candidate(session)
    svc = CandidateStrategyProposalService(session)
    return await svc.create(candidate.id, source="manual")


@pytest.mark.asyncio
async def test_approve_and_prepare_one_click(db_session: AsyncSession):
    proposal = await _pending_proposal(db_session)
    svc = CandidateStrategyProposalService(db_session)
    await svc.review(proposal.id, status="approved", reviewed_by="tester")

    prepared, readiness = await CandidateProposalExperimentService(
        db_session
    ).approve_and_prepare(proposal.id, confirmed_by="tester")

    # 준비 완료 + readiness 기록까지 한 번에
    assert prepared.experiment_id is not None
    assert readiness.ready is True
    assert readiness.ready_by == "tester"
    # 안전: 전부 DRAFT + auto_trade off — runner가 절대 안 잡는다
    assert prepared.strategy_version_status == StrategyVersionStatus.DRAFT.value
    assert prepared.experiment_status == "draft"
    assert prepared.auto_trade_enabled is False
    assert all(s == "draft" for s in readiness.strategy_version_statuses)
    assert not any(readiness.auto_trade_enabled_values)


@pytest.mark.asyncio
async def test_approve_and_prepare_requires_approved(db_session: AsyncSession):
    proposal = await _pending_proposal(db_session)  # 여전히 pending
    with pytest.raises(ProposalNotApprovedError):
        await CandidateProposalExperimentService(db_session).approve_and_prepare(
            proposal.id
        )


@pytest.mark.asyncio
async def test_approve_and_prepare_idempotent(db_session: AsyncSession):
    proposal = await _pending_proposal(db_session)
    svc = CandidateStrategyProposalService(db_session)
    await svc.review(proposal.id, status="approved", reviewed_by="tester")
    exp_svc = CandidateProposalExperimentService(db_session)

    first, _ = await exp_svc.approve_and_prepare(proposal.id, confirmed_by="tester")
    second, readiness2 = await exp_svc.approve_and_prepare(proposal.id, confirmed_by="tester")

    assert second.experiment_id == first.experiment_id
    assert second.already_prepared is True
    assert readiness2.already_ready is True


@pytest.mark.asyncio
async def test_review_without_flag_unchanged(db_session: AsyncSession):
    """플래그 없는 기존 승인 경로: 상태만 변경, 실험 준비 없음 (하위호환)."""
    proposal = await _pending_proposal(db_session)
    svc = CandidateStrategyProposalService(db_session)
    reviewed = await svc.review(proposal.id, status="approved", reviewed_by="tester")
    assert reviewed.status == "approved"
    assert reviewed.experiment_id is None
    assert reviewed.prepared_at is None
