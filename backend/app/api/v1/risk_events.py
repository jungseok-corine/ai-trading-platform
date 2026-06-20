"""리스크 이벤트 요약 API (C-3.12).

리스크 레이어의 승인/차단 기록을 룰별·최근 차단 목록으로 집계해 반환한다.
read-only 집계로 주문/외부 호출이 없다.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.risk_event_summary_service import RiskEventSummaryService

router = APIRouter(prefix="/risk-events", tags=["risk-events"])


def get_service(session: AsyncSession = Depends(get_db)) -> RiskEventSummaryService:
    return RiskEventSummaryService(session)


@router.get("/summary")
async def get_summary(
    days: int = Query(30, ge=1, le=365),
    service: RiskEventSummaryService = Depends(get_service),
) -> dict:
    return await service.summary(days=days)
