"""자율 연구 루프 관제탑 상태 API (C-2.43).

각 자율 잡의 최근 실행 + 검토 대기 제안 수 + 활성 버전 수를 한 번에 반환한다.
read-only 집계로 주문/외부 호출이 없다.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.research_status_service import ResearchStatusService

router = APIRouter(prefix="/research-status", tags=["research-status"])


def get_service(session: AsyncSession = Depends(get_db)) -> ResearchStatusService:
    return ResearchStatusService(session)


class JobStatusRead(BaseModel):
    job_id: str
    last_run_at: str | None
    status: str | None
    duration_ms: int | None
    error_message: str | None


class ResearchStatusRead(BaseModel):
    jobs: list[JobStatusRead]
    pending: dict
    active: dict


@router.get("", response_model=ResearchStatusRead)
async def get_status(
    service: ResearchStatusService = Depends(get_service),
) -> ResearchStatusRead:
    status = await service.status()
    return ResearchStatusRead(**status.to_dict())
