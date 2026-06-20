"""일일 AI 분석 잡 API (C-2.54).

활성 전략 버전을 활동량 게이트로 선별해 분석을 일괄 실행한다. provider/model/mode는
설정에서 읽으며, 기본 provider는 fake(실수로 유료 호출 방지). 사람이 명시적으로 켠다.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.daily_analysis_service import DailyAnalysisService
from app.trading.strategy.schemas import SchedulerRunRead

router = APIRouter(prefix="/daily-analysis", tags=["daily-analysis"])


def get_service(session: AsyncSession = Depends(get_db)) -> DailyAnalysisService:
    return DailyAnalysisService(session)


class DailyAnalysisSummaryRead(BaseModel):
    trading_day: str
    versions: int
    analyzed: int
    skipped: int
    mode: str
    provider: str
    per_version: list[dict]


@router.post("/run", response_model=DailyAnalysisSummaryRead, status_code=201)
async def run_daily_analysis(
    trading_day: date | None = Query(default=None, description="KST 거래일 (기본 오늘)"),
    service: DailyAnalysisService = Depends(get_service),
) -> DailyAnalysisSummaryRead:
    """활성 전략 버전을 활동량 게이트로 선별해 분석하고 이력을 남긴다."""
    summary = await service.run_and_record(trading_day=trading_day)
    return DailyAnalysisSummaryRead(**summary.to_dict())


@router.get("/runs", response_model=list[SchedulerRunRead])
async def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    service: DailyAnalysisService = Depends(get_service),
) -> list[SchedulerRunRead]:
    runs = await service.list_runs(limit=limit)
    return [SchedulerRunRead.model_validate(r) for r in runs]
