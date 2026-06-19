"""자율 연구 파이프라인 API (C-2.35).

스캔 → 후보 발견 → 전략 배정을 한 번에 실행한다. 메타데이터 작업이며 주문과 무관하다.
"""
from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.research_pipeline_service import ResearchPipelineService

router = APIRouter(prefix="/research-pipeline", tags=["research-pipeline"])


def get_service(session: AsyncSession = Depends(get_db)) -> ResearchPipelineService:
    return ResearchPipelineService(session)


class PipelineRunRequest(BaseModel):
    # None이면 enabled watchlist 종목 전체를 대상으로 한다.
    symbol_codes: list[str] | None = None
    auto_assign: bool = True


class VersionRunRead(BaseModel):
    scanner_rule_version_id: int
    scanned: int
    matched: int
    assigned: int


class PipelineSummaryRead(BaseModel):
    versions: int
    symbols: int
    candidates: int
    assignments: int
    per_version: list[VersionRunRead]


@router.post("/run", response_model=PipelineSummaryRead, status_code=201)
async def run_pipeline(
    payload: PipelineRunRequest,
    service: ResearchPipelineService = Depends(get_service),
) -> PipelineSummaryRead:
    """active/testing 스캐너 버전을 1회 실행해 후보 발견 + 전략 배정을 수행한다."""
    summary = await service.run_once(
        symbol_codes=payload.symbol_codes, auto_assign=payload.auto_assign
    )
    return PipelineSummaryRead(
        versions=summary.versions,
        symbols=summary.symbols,
        candidates=summary.candidates,
        assignments=summary.assignments,
        per_version=[
            VersionRunRead(
                scanner_rule_version_id=v.scanner_rule_version_id,
                scanned=v.scanned,
                matched=v.matched,
                assigned=v.assigned,
            )
            for v in summary.per_version
        ],
    )
