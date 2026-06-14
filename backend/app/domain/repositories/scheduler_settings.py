from sqlalchemy import select

from app.domain.models.scheduler_settings import SchedulerSettings
from app.domain.repositories.base import BaseRepository

SCHEDULER_SETTINGS_ID = 1


class SchedulerSettingsRepository(BaseRepository[SchedulerSettings]):
    model = SchedulerSettings

    async def get_singleton(self) -> SchedulerSettings | None:
        result = await self.session.execute(
            select(SchedulerSettings).where(SchedulerSettings.id == SCHEDULER_SETTINGS_ID)
        )
        return result.scalar_one_or_none()
