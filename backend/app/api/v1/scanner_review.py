"""스캐너 룰 자동 점검 API (C-2.40).

active/testing 스캐너 버전의 후보 성과를 분석해 '조건 강화' 제안을 일괄 생성한다(pending).
승인 전에는 룰에 반영되지 않으며, 주문/외부 API 호출이 없는 메타 작업이다.
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.scanner_review_service import ScannerReviewService
from app.trading.strategy.schemas import SchedulerRunRead

router = APIRouter(prefix="/scanner-review", tags=["scanner-review"])


def get_service(session: AsyncSession = Depends(get_db)) -> ScannerReviewService:
    return ScannerReviewService(session)


class ReviewRequest(BaseModel):
    horizon_minutes: int = 30


class ReviewSummaryRead(BaseModel):
    versions_reviewed: int
    proposals_created: int
    skipped_existing: int
    created_proposal_ids: list[int]


@router.post("/run", response_model=ReviewSummaryRead, status_code=201)
async def run_review(
    payload: ReviewRequest,
    service: ScannerReviewService = Depends(get_service),
) -> ReviewSummaryRead:
    """active/testing 스캐너 버전을 점검해 조건 강화 제안을 일괄 생성하고 이력을 남긴다."""
    summary = await service.review_and_record(horizon_minutes=payload.horizon_minutes)
    return ReviewSummaryRead(
        versions_reviewed=summary.versions_reviewed,
        proposals_created=summary.proposals_created,
        skipped_existing=summary.skipped_existing,
        created_proposal_ids=summary.created_proposal_ids,
    )


@router.get("/runs", response_model=list[SchedulerRunRead])
async def list_review_runs(
    limit: int = Query(default=20, ge=1, le=100),
    service: ScannerReviewService = Depends(get_service),
) -> list[SchedulerRunRead]:
    """점검 실행 이력(수동+스케줄)을 최신순으로 반환한다."""
    runs = await service.list_runs(limit=limit)
    return [SchedulerRunRead.model_validate(r) for r in runs]
