"""전략 버전 자동 점검 API (C-2.42).

active/testing 전략 버전의 거래 성과를 분석해 파라미터 조정 제안을 일괄 생성한다(pending).
승인 전에는 전략에 반영되지 않으며 auto_trade도 켜지 않는다. 주문이 없는 메타 작업이다.
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.strategy_review_service import StrategyReviewService
from app.trading.strategy.schemas import SchedulerRunRead

router = APIRouter(prefix="/strategy-review", tags=["strategy-review"])


def get_service(session: AsyncSession = Depends(get_db)) -> StrategyReviewService:
    return StrategyReviewService(session)


class ReviewSummaryRead(BaseModel):
    versions_reviewed: int
    proposals_created: int
    skipped_existing: int
    created_proposal_ids: list[int]


@router.post("/run", response_model=ReviewSummaryRead, status_code=201)
async def run_review(
    service: StrategyReviewService = Depends(get_service),
) -> ReviewSummaryRead:
    """active/testing 전략 버전을 점검해 개선 제안을 일괄 생성하고 이력을 남긴다."""
    summary = await service.review_and_record()
    return ReviewSummaryRead(
        versions_reviewed=summary.versions_reviewed,
        proposals_created=summary.proposals_created,
        skipped_existing=summary.skipped_existing,
        created_proposal_ids=summary.created_proposal_ids,
    )


@router.get("/runs", response_model=list[SchedulerRunRead])
async def list_review_runs(
    limit: int = Query(default=20, ge=1, le=100),
    service: StrategyReviewService = Depends(get_service),
) -> list[SchedulerRunRead]:
    """점검 실행 이력(수동+스케줄)을 최신순으로 반환한다."""
    runs = await service.list_runs(limit=limit)
    return [SchedulerRunRead.model_validate(r) for r in runs]
