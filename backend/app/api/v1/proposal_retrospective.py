"""AI 제안 회고 API (C-2.46).

승인된 제안이 만든 새 버전이 base 버전 대비 성과를 개선했는지 회고한다.
read-only 집계로 주문/외부 호출이 없다.
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.proposal_retrospective_service import ProposalRetrospectiveService

router = APIRouter(prefix="/proposal-retrospective", tags=["proposal-retrospective"])


def get_service(session: AsyncSession = Depends(get_db)) -> ProposalRetrospectiveService:
    return ProposalRetrospectiveService(session)


class RetroEntryRead(BaseModel):
    proposal_id: int
    kind: str
    base_version_id: int | None
    created_version_id: int | None
    metric: str
    base_metric: float | None
    new_metric: float | None
    base_samples: int
    new_samples: int
    verdict: str


@router.get("/strategy", response_model=list[RetroEntryRead])
async def list_strategy_retros(
    limit: int = Query(default=100, ge=1, le=500),
    service: ProposalRetrospectiveService = Depends(get_service),
) -> list[RetroEntryRead]:
    retros = await service.list_strategy_retros(limit=limit)
    return [RetroEntryRead(**r.to_dict()) for r in retros]


@router.get("/scanner", response_model=list[RetroEntryRead])
async def list_scanner_retros(
    limit: int = Query(default=100, ge=1, le=500),
    service: ProposalRetrospectiveService = Depends(get_service),
) -> list[RetroEntryRead]:
    retros = await service.list_scanner_retros(limit=limit)
    return [RetroEntryRead(**r.to_dict()) for r in retros]


@router.get("/summary")
async def get_summary(
    service: ProposalRetrospectiveService = Depends(get_service),
) -> dict:
    return await service.summary()


@router.get("/backtest-accuracy")
async def get_backtest_accuracy(
    limit: int = 100,
    service: ProposalRetrospectiveService = Depends(get_service),
) -> dict:
    """백테스트 예측 적중률 (C-6.13) — 백테스트 verdict vs 실제 회고 판정."""
    return await service.backtest_accuracy(limit=limit)
