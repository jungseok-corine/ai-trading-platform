"""스캐너 룰 개선 제안(AI Proposal) API (C-2.39).

후보 성과 분석을 근거로 스캐너 '조건 강화' 제안을 저장하고, 사람이 승인할 때만 새
scanner_rule_version(DRAFT)을 생성한다. AI는 룰을 직접 활성화하거나 실거래를 켤 수 없다.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import ProposalStatus
from app.services.scanner_proposal_generator import ScannerProposalGenerator
from app.services.scanner_proposal_service import (
    ScannerProposalNotFoundError,
    ScannerProposalNotPendingError,
    ScannerProposalService,
)
from app.services.scanner_service import (
    ScannerRuleNotFoundError,
    ScannerRuleVersionNotFoundError,
)
from app.trading.scanner.conditions import InvalidConditionError

router = APIRouter(prefix="/scanner-proposals", tags=["scanner-proposals"])


def get_service(session: AsyncSession = Depends(get_db)) -> ScannerProposalService:
    return ScannerProposalService(session)


def get_generator(session: AsyncSession = Depends(get_db)) -> ScannerProposalGenerator:
    return ScannerProposalGenerator(session)


# --- schemas ---------------------------------------------------------------
class ScannerProposalCreateRequest(BaseModel):
    scanner_rule_id: int
    suggested_conditions: list[dict]
    title: str
    summary: str | None = None
    rationale: str | None = None
    expected_effect: str | None = None
    risk_notes: str | None = None
    base_version_id: int | None = None
    source: str = "ai"


class ScannerProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scanner_rule_id: int
    base_version_id: int | None
    title: str
    summary: str | None
    rationale: str | None
    expected_effect: str | None
    risk_notes: str | None
    suggested_conditions: list[dict]
    source: str
    status: ProposalStatus
    created_version_id: int | None
    reviewed_by: str | None
    review_note: str | None
    reviewed_at: datetime | None
    created_at: datetime


class ConditionDiffRead(BaseModel):
    type: str
    before: Any = None
    after: Any = None


class ScannerProposalDetailRead(ScannerProposalRead):
    diff: list[ConditionDiffRead] = []


class ReviewRequest(BaseModel):
    reviewed_by: str | None = None
    review_note: str | None = None


class BulkReviewRequest(BaseModel):
    proposal_ids: list[int]
    action: str  # "approve" | "reject"
    reviewed_by: str | None = None
    review_note: str | None = None


class GenerateRequest(BaseModel):
    version_id: int
    horizon_minutes: int = 30


class ApproveResponse(BaseModel):
    proposal: ScannerProposalRead
    created_version_id: int


# --- endpoints -------------------------------------------------------------
@router.post("", response_model=ScannerProposalRead, status_code=201)
async def create_proposal(
    payload: ScannerProposalCreateRequest,
    service: ScannerProposalService = Depends(get_service),
) -> ScannerProposalRead:
    try:
        proposal = await service.create_proposal(
            scanner_rule_id=payload.scanner_rule_id,
            suggested_conditions=payload.suggested_conditions,
            title=payload.title,
            summary=payload.summary,
            rationale=payload.rationale,
            expected_effect=payload.expected_effect,
            risk_notes=payload.risk_notes,
            base_version_id=payload.base_version_id,
            source=payload.source,
        )
    except ScannerRuleNotFoundError as e:
        raise HTTPException(status_code=404, detail="scanner rule not found") from e
    except ScannerRuleVersionNotFoundError as e:
        raise HTTPException(status_code=404, detail="scanner rule version not found") from e
    except InvalidConditionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return ScannerProposalRead.model_validate(proposal)


@router.post("/generate", response_model=ScannerProposalRead)
async def generate_proposal(
    payload: GenerateRequest,
    generator: ScannerProposalGenerator = Depends(get_generator),
):
    """룰 버전의 후보 성과를 분석해 '조건 강화' 제안을 자동 생성한다(pending).

    제안할 변경이 없으면(데이터 부족 또는 승률이 기준 이상) 204를 반환한다.
    """
    try:
        proposal = await generator.generate_for_version(
            payload.version_id, payload.horizon_minutes
        )
    except ScannerRuleVersionNotFoundError as e:
        raise HTTPException(status_code=404, detail="scanner rule version not found") from e
    if proposal is None:
        return Response(status_code=204)
    return ScannerProposalRead.model_validate(proposal)


@router.post("/bulk-review")
async def bulk_review(
    payload: BulkReviewRequest,
    service: ScannerProposalService = Depends(get_service),
) -> dict:
    """여러 스캐너 제안을 한 번에 승인/거절한다(개별 실패는 결과에 격리)."""
    try:
        return await service.bulk_review(
            payload.proposal_ids, payload.action,
            reviewed_by=payload.reviewed_by, review_note=payload.review_note,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("", response_model=list[ScannerProposalRead])
async def list_proposals(
    scanner_rule_id: int | None = Query(default=None),
    status: ProposalStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: ScannerProposalService = Depends(get_service),
) -> list[ScannerProposalRead]:
    proposals = await service.list_proposals(
        scanner_rule_id=scanner_rule_id, status=status, limit=limit, offset=offset
    )
    return [ScannerProposalRead.model_validate(p) for p in proposals]


@router.get("/{proposal_id}", response_model=ScannerProposalDetailRead)
async def get_proposal(
    proposal_id: int, service: ScannerProposalService = Depends(get_service)
) -> ScannerProposalDetailRead:
    proposal = await service.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    diff = await service.diff_for(proposal)
    detail = ScannerProposalDetailRead.model_validate(proposal)
    detail.diff = [
        ConditionDiffRead(type=d.type, before=d.before, after=d.after) for d in diff
    ]
    return detail


@router.post("/{proposal_id}/approve", response_model=ApproveResponse)
async def approve_proposal(
    proposal_id: int,
    payload: ReviewRequest,
    service: ScannerProposalService = Depends(get_service),
) -> ApproveResponse:
    """제안을 승인하고 새 DRAFT 룰 버전을 생성한다(자동 활성화 금지)."""
    try:
        proposal, version = await service.approve(
            proposal_id, reviewed_by=payload.reviewed_by, review_note=payload.review_note
        )
    except ScannerProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail="proposal not found") from e
    except ScannerProposalNotPendingError as e:
        raise HTTPException(status_code=409, detail="proposal already reviewed") from e
    return ApproveResponse(
        proposal=ScannerProposalRead.model_validate(proposal),
        created_version_id=version.id,
    )


@router.post("/{proposal_id}/reject", response_model=ScannerProposalRead)
async def reject_proposal(
    proposal_id: int,
    payload: ReviewRequest,
    service: ScannerProposalService = Depends(get_service),
) -> ScannerProposalRead:
    try:
        proposal = await service.reject(
            proposal_id, reviewed_by=payload.reviewed_by, review_note=payload.review_note
        )
    except ScannerProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail="proposal not found") from e
    except ScannerProposalNotPendingError as e:
        raise HTTPException(status_code=409, detail="proposal already reviewed") from e
    return ScannerProposalRead.model_validate(proposal)
