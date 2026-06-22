"""자율 잡 제어판 API (C-4.7).

웹에서 연구/분석 자율 잡을 ON/OFF 토글하고 즉시 실행한다. 상태는 DB에 영속되어
.env를 못 만지는 환경에서도 웹으로 제어할 수 있고 재시작에도 유지된다.
모두 read-only 연구/집계 잡이며 주문과 무관하다. 기본값은 여전히 OFF.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.services.scheduler_control_service import (
    AutonomousJobStatus,
    SchedulerControlService,
    UnknownJobError,
)

router = APIRouter(prefix="/autonomous-jobs", tags=["autonomous-jobs"])


class AutonomousJobRead(BaseModel):
    job_id: str
    label: str
    schedule: str
    enabled: bool
    overridden: bool
    running: bool
    last_run_at: datetime | None = None
    last_error: str | None = None


class ToggleRequest(BaseModel):
    enabled: bool


def _to_read(s: AutonomousJobStatus) -> AutonomousJobRead:
    return AutonomousJobRead(
        job_id=s.job_id, label=s.label, schedule=s.schedule, enabled=s.enabled,
        overridden=s.overridden, running=s.running, last_run_at=s.last_run_at, last_error=s.last_error,
    )


@router.get("", response_model=list[AutonomousJobRead])
async def list_autonomous_jobs(
    request: Request, session: AsyncSession = Depends(get_db)
) -> list[AutonomousJobRead]:
    settings = get_settings()
    jobs = await SchedulerControlService(session).list_jobs(request.app, settings)
    return [_to_read(j) for j in jobs]


@router.patch("/{job_id}", response_model=AutonomousJobRead)
async def toggle_autonomous_job(
    job_id: str, payload: ToggleRequest, request: Request, session: AsyncSession = Depends(get_db)
) -> AutonomousJobRead:
    settings = get_settings()
    service = SchedulerControlService(session)
    try:
        await service.set_enabled(job_id, payload.enabled, request.app, settings)
    except UnknownJobError:
        raise HTTPException(status_code=404, detail=f"unknown job_id: {job_id}")
    jobs = await service.list_jobs(request.app, settings)
    return next(_to_read(j) for j in jobs if j.job_id == job_id)


@router.post("/{job_id}/run")
async def run_autonomous_job(
    job_id: str, request: Request, session: AsyncSession = Depends(get_db)
) -> dict:
    try:
        await SchedulerControlService(session).run_now(job_id, request.app)
    except UnknownJobError:
        raise HTTPException(status_code=404, detail=f"unknown job_id: {job_id}")
    return {"status": "ok", "job_id": job_id}
