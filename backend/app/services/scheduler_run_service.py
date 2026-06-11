from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import SchedulerRunStatus
from app.domain.models.scheduler_run import SchedulerRun
from app.domain.repositories.scheduler_run import SchedulerRunRepository


class SchedulerRunService:
    """scheduler job(strategy_runner, order_sync) 1회 실행에 대한 기록을 저장/조회한다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SchedulerRunRepository(session)

    async def record_run(
        self,
        job_id: str,
        started_at: datetime,
        finished_at: datetime,
        status: SchedulerRunStatus,
        error_message: str | None = None,
        summary: dict | None = None,
    ) -> SchedulerRun:
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        run = await self._repo.create(
            job_id=job_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            error_message=error_message,
            summary=summary,
        )
        await self._session.commit()
        return run

    async def list_recent(self, limit: int = 20) -> list[SchedulerRun]:
        return await self._repo.list_recent(limit)

    async def has_recent_failure(self, limit: int = 20) -> bool:
        return await self._repo.has_recent_failure(limit)
