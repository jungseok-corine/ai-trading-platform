from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.scheduler_job_override import SchedulerJobOverride
from app.scheduler.registry import CONTROLLABLE_BY_ID, CONTROLLABLE_JOBS, apply_job_enabled


class UnknownJobError(Exception):
    """제어 대상이 아닌 job_id를 토글/실행하려 할 때 발생."""


@dataclass
class AutonomousJobStatus:
    job_id: str
    label: str
    schedule: str
    enabled: bool
    overridden: bool  # DB 오버라이드로 설정됐는지(아니면 env 기본값)
    running: bool  # 현재 scheduler에 등록돼 있는지
    last_run_at: datetime | None
    last_error: str | None


class SchedulerControlService:
    """자율 잡의 활성화 상태를 DB 오버라이드로 영속하고 런타임 scheduler에 반영한다.

    오버라이드 행이 없으면 env 기본값(`*_scheduler_enabled`, 기본 OFF)을 따른다.
    → 빈 테이블 = 전부 기본값 = 안전 불변식(새 잡 기본 비활성) 유지.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _overrides(self) -> dict[str, bool]:
        rows = (await self._session.execute(select(SchedulerJobOverride))).scalars().all()
        return {r.job_id: r.enabled for r in rows}

    async def effective_enabled_map(self, settings: Any) -> dict[str, bool]:
        """각 자율 잡의 실효 활성 상태(오버라이드 우선, 없으면 env 기본값)."""
        overrides = await self._overrides()
        return {
            job.job_id: overrides.get(job.job_id, job.env_enabled(settings))
            for job in CONTROLLABLE_JOBS
        }

    async def list_jobs(self, app: FastAPI, settings: Any) -> list[AutonomousJobStatus]:
        overrides = await self._overrides()
        scheduler = getattr(app.state, "scheduler", None)
        running_ids = {job.id for job in scheduler.get_jobs()} if scheduler is not None else set()
        result: list[AutonomousJobStatus] = []
        for job in CONTROLLABLE_JOBS:
            enabled = overrides.get(job.job_id, job.env_enabled(settings))
            result.append(
                AutonomousJobStatus(
                    job_id=job.job_id,
                    label=job.label_ko,
                    schedule=job.schedule_desc,
                    enabled=enabled,
                    overridden=job.job_id in overrides,
                    running=job.job_id in running_ids,
                    last_run_at=getattr(app.state, f"{job.job_id}_last_run_at", None),
                    last_error=getattr(app.state, f"{job.job_id}_last_error", None),
                )
            )
        return result

    async def set_enabled(self, job_id: str, enabled: bool, app: FastAPI, settings: Any) -> None:
        job = CONTROLLABLE_BY_ID.get(job_id)
        if job is None:
            raise UnknownJobError(job_id)
        existing = await self._session.get(SchedulerJobOverride, job_id)
        if existing is not None:
            existing.enabled = enabled
        else:
            self._session.add(SchedulerJobOverride(job_id=job_id, enabled=enabled))
        await self._session.commit()
        apply_job_enabled(app, settings, job, enabled)

    async def run_now(self, job_id: str, app: FastAPI) -> None:
        job = CONTROLLABLE_BY_ID.get(job_id)
        if job is None:
            raise UnknownJobError(job_id)
        await job.func(app)
