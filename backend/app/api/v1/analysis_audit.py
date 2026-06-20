"""AI 분석 실행 감사 API (C-3.4).

최근 분석 run을 실행 메타 + 토큰/추정비용 + 생성 제안 수와 함께 반환한다.
read-only 집계로 주문/외부 호출이 없다.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.analysis_audit_service import AnalysisAuditService

router = APIRouter(prefix="/analysis-audit", tags=["analysis-audit"])


def get_service(session: AsyncSession = Depends(get_db)) -> AnalysisAuditService:
    return AnalysisAuditService(session)


@router.get("")
async def get_recent(
    limit: int = Query(20, ge=1, le=100),
    service: AnalysisAuditService = Depends(get_service),
) -> list[dict]:
    return await service.recent(limit=limit)
