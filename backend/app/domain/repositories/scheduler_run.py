from sqlalchemy import select

from app.domain.models.enums import SchedulerRunStatus
from app.domain.models.scheduler_run import SchedulerRun
from app.domain.repositories.base import BaseRepository


class SchedulerRunRepository(BaseRepository[SchedulerRun]):
    model = SchedulerRun

    async def list_recent(self, limit: int = 20) -> list[SchedulerRun]:
        result = await self.session.execute(
            select(SchedulerRun).order_by(SchedulerRun.started_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_job(self, job_id: str, limit: int = 20) -> list[SchedulerRun]:
        result = await self.session.execute(
            select(SchedulerRun)
            .where(SchedulerRun.job_id == job_id)
            .order_by(SchedulerRun.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def has_recent_failure(self, limit: int = 20) -> bool:
        recent = await self.list_recent(limit)
        return any(run.status == SchedulerRunStatus.FAILED for run in recent)
