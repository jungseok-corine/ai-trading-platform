"""GET /api/v1/analysis-runs/{run_id} — 단일 분석 run 조회."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.ai_analysis.run_schemas import AnalysisRunRead
from app.services.ai_analysis.run_service import AnalysisRunService

router = APIRouter(prefix="/analysis-runs", tags=["analysis-runs"])


def get_run_service(session: AsyncSession = Depends(get_db)) -> AnalysisRunService:
    return AnalysisRunService(session)


@router.get("/{run_id}", response_model=AnalysisRunRead)
async def get_analysis_run(
    run_id: int,
    service: AnalysisRunService = Depends(get_run_service),
) -> AnalysisRunRead:
    """분석 run을 조회한다. responses(모델 응답 목록)를 포함한다."""
    run = await service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="analysis run not found")
    return AnalysisRunRead.model_validate(run)
