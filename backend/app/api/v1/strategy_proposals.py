"""전략 개선 제안(AI Proposal) API (C-2.27).

AI/수동 제안을 저장하고, 사람이 승인할 때만 새 strategy_version(DRAFT)을 생성한다.
승인으로 생성되는 버전은 항상 auto_trade_enabled=False다(AI 자동 활성화 금지).
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import ProposalStatus
from app.services.proposal_generator import ProposalGeneratorService
from app.services.proposal_service import (
    InvalidProposalError,
    ProposalNotFoundError,
    ProposalNotPendingError,
    ProposalService,
)
from app.services.status_transition_planner import (
    PlannerProposalNotFoundError,
    StatusTransitionPlannerService,
)
from app.services.strategy_service import (
    StrategyNotFoundError,
    StrategyVersionNotFoundError,
)

router = APIRouter(prefix="/strategy-proposals", tags=["strategy-proposals"])


def get_service(session: AsyncSession = Depends(get_db)) -> ProposalService:
    return ProposalService(session)


def get_generator(session: AsyncSession = Depends(get_db)) -> ProposalGeneratorService:
    return ProposalGeneratorService(session)


# --- schemas ---------------------------------------------------------------
class ProposalCreateRequest(BaseModel):
    strategy_id: int
    suggested_parameters: dict
    title: str
    summary: str | None = None
    rationale: str | None = None
    expected_effect: str | None = None
    risk_notes: str | None = None
    base_version_id: int | None = None
    source: str = "ai"
    ai_analysis_run_id: int | None = None


class ProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    base_version_id: int | None
    ai_analysis_run_id: int | None
    title: str
    summary: str | None
    rationale: str | None
    expected_effect: str | None
    risk_notes: str | None
    suggested_parameters: dict
    source: str
    status: ProposalStatus
    created_version_id: int | None
    reviewed_by: str | None
    review_note: str | None
    reviewed_at: datetime | None
    created_at: datetime


class ParamDiffRead(BaseModel):
    key: str
    before: Any = None
    after: Any = None


class ProposalDetailRead(ProposalRead):
    diff: list[ParamDiffRead] = []


class ReviewRequest(BaseModel):
    reviewed_by: str | None = None
    review_note: str | None = None


class BulkReviewRequest(BaseModel):
    proposal_ids: list[int]
    action: str  # "approve" | "reject"
    reviewed_by: str | None = None
    review_note: str | None = None


class GenerateRequest(BaseModel):
    strategy_id: int
    version_id: int
    ai_analysis_run_id: int | None = None


class ApproveResponse(BaseModel):
    proposal: ProposalRead
    created_version_id: int


class TransitionPlanRead(BaseModel):
    proposal_id: int
    proposal_type: str
    new_version: dict
    previous_versions: list[dict]
    blocked_actions: list[dict]
    safety_warnings: list[str]
    plan_valid: bool


def get_planner(session: AsyncSession = Depends(get_db)) -> StatusTransitionPlannerService:
    return StatusTransitionPlannerService(session)


# --- endpoints -------------------------------------------------------------
@router.post("", response_model=ProposalRead, status_code=201)
async def create_proposal(
    payload: ProposalCreateRequest, service: ProposalService = Depends(get_service)
) -> ProposalRead:
    try:
        proposal = await service.create_proposal(
            strategy_id=payload.strategy_id,
            suggested_parameters=payload.suggested_parameters,
            title=payload.title,
            summary=payload.summary,
            rationale=payload.rationale,
            expected_effect=payload.expected_effect,
            risk_notes=payload.risk_notes,
            base_version_id=payload.base_version_id,
            source=payload.source,
            ai_analysis_run_id=payload.ai_analysis_run_id,
        )
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail="strategy not found") from e
    except InvalidProposalError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return ProposalRead.model_validate(proposal)


@router.post("/generate", response_model=ProposalRead)
async def generate_proposal(
    payload: GenerateRequest,
    generator: ProposalGeneratorService = Depends(get_generator),
):
    """전략 버전 성과를 분석해 개선 제안을 자동 생성한다(pending).

    제안할 변경이 없으면(데이터 부족 또는 기대값 양수) 204를 반환한다.
    """
    try:
        proposal = await generator.generate_for_version(
            payload.strategy_id, payload.version_id, payload.ai_analysis_run_id
        )
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail="strategy not found") from e
    except StrategyVersionNotFoundError as e:
        raise HTTPException(status_code=404, detail="strategy version not found") from e
    if proposal is None:
        return Response(status_code=204)
    return ProposalRead.model_validate(proposal)


@router.post("/bulk-review")
async def bulk_review(
    payload: BulkReviewRequest,
    service: ProposalService = Depends(get_service),
) -> dict:
    """여러 전략 제안을 한 번에 승인/거절한다(개별 실패는 결과에 격리)."""
    try:
        return await service.bulk_review(
            payload.proposal_ids, payload.action,
            reviewed_by=payload.reviewed_by, review_note=payload.review_note,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("", response_model=list[ProposalRead])
async def list_proposals(
    strategy_id: int | None = Query(default=None),
    status: ProposalStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: ProposalService = Depends(get_service),
) -> list[ProposalRead]:
    proposals = await service.list_proposals(
        strategy_id=strategy_id, status=status, limit=limit, offset=offset
    )
    return [ProposalRead.model_validate(p) for p in proposals]


@router.get("/{proposal_id}", response_model=ProposalDetailRead)
async def get_proposal(
    proposal_id: int, service: ProposalService = Depends(get_service)
) -> ProposalDetailRead:
    proposal = await service.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    diff = await service.diff_for(proposal)
    detail = ProposalDetailRead.model_validate(proposal)
    detail.diff = [ParamDiffRead(key=d.key, before=d.before, after=d.after) for d in diff]
    return detail


@router.post("/{proposal_id}/approve", response_model=ApproveResponse)
async def approve_proposal(
    proposal_id: int,
    payload: ReviewRequest,
    service: ProposalService = Depends(get_service),
) -> ApproveResponse:
    """제안을 승인하고 새 DRAFT 버전을 생성한다(auto_trade_enabled=False 강제)."""
    try:
        proposal, version = await service.approve(
            proposal_id, reviewed_by=payload.reviewed_by, review_note=payload.review_note
        )
    except ProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail="proposal not found") from e
    except ProposalNotPendingError as e:
        raise HTTPException(status_code=409, detail="proposal already reviewed") from e
    return ApproveResponse(
        proposal=ProposalRead.model_validate(proposal), created_version_id=version.id
    )


@router.post("/{proposal_id}/reject", response_model=ProposalRead)
async def reject_proposal(
    proposal_id: int,
    payload: ReviewRequest,
    service: ProposalService = Depends(get_service),
) -> ProposalRead:
    try:
        proposal = await service.reject(
            proposal_id, reviewed_by=payload.reviewed_by, review_note=payload.review_note
        )
    except ProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail="proposal not found") from e
    except ProposalNotPendingError as e:
        raise HTTPException(status_code=409, detail="proposal already reviewed") from e
    return ProposalRead.model_validate(proposal)


@router.get("/{proposal_id}/transition-plan", response_model=TransitionPlanRead)
async def get_transition_plan(
    proposal_id: int,
    planner: StatusTransitionPlannerService = Depends(get_planner),
) -> TransitionPlanRead:
    """제안 승인 시 발생할 버전 상태 전환 계획을 반환한다 (read-only, deterministic)."""
    try:
        plan = await planner.plan_for_strategy_proposal(proposal_id)
    except PlannerProposalNotFoundError:
        raise HTTPException(status_code=404, detail="proposal not found")
    return TransitionPlanRead(**plan.to_dict())
