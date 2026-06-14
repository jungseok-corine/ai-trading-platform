from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.scheduler_settings import SchedulerSettings
from app.domain.repositories.scheduler_settings import SCHEDULER_SETTINGS_ID, SchedulerSettingsRepository

MIN_STRATEGY_INTERVAL_SECONDS = 60
MIN_ORDER_SYNC_INTERVAL_SECONDS = 60


class InvalidSchedulerIntervalError(ValueError):
    """스케줄러 주기가 허용 최소값보다 작을 때 발생한다."""


class SchedulerSettingsService:
    """strategy_runner/order_sync 스케줄러 주기 설정을 조회/수정한다.

    설정이 DB에 없으면 app.core.config의 기본값으로 singleton row를 생성한다.
    KIS 모의투자 API 호출 제한(EGW00201)을 고려해 두 작업 모두 최소 60초 간격을
    강제한다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SchedulerSettingsRepository(session)

    async def get_settings(self) -> SchedulerSettings:
        settings = await self._repo.get_singleton()
        if settings is not None:
            return settings

        defaults = get_settings()
        created = await self._repo.create(
            id=SCHEDULER_SETTINGS_ID,
            strategy_scheduler_interval_seconds=defaults.strategy_scheduler_interval_seconds,
            order_sync_scheduler_interval_seconds=defaults.order_sync_scheduler_interval_seconds,
        )
        await self._session.commit()
        return created

    async def update_settings(
        self,
        strategy_scheduler_interval_seconds: int | None = None,
        order_sync_scheduler_interval_seconds: int | None = None,
    ) -> SchedulerSettings:
        if (
            strategy_scheduler_interval_seconds is not None
            and strategy_scheduler_interval_seconds < MIN_STRATEGY_INTERVAL_SECONDS
        ):
            raise InvalidSchedulerIntervalError(
                f"strategy_scheduler_interval_seconds는 {MIN_STRATEGY_INTERVAL_SECONDS}초 이상이어야 합니다."
            )
        if (
            order_sync_scheduler_interval_seconds is not None
            and order_sync_scheduler_interval_seconds < MIN_ORDER_SYNC_INTERVAL_SECONDS
        ):
            raise InvalidSchedulerIntervalError(
                f"order_sync_scheduler_interval_seconds는 {MIN_ORDER_SYNC_INTERVAL_SECONDS}초 이상이어야 합니다."
            )

        settings = await self.get_settings()
        updates: dict[str, int] = {}
        if strategy_scheduler_interval_seconds is not None:
            updates["strategy_scheduler_interval_seconds"] = strategy_scheduler_interval_seconds
        if order_sync_scheduler_interval_seconds is not None:
            updates["order_sync_scheduler_interval_seconds"] = order_sync_scheduler_interval_seconds

        if not updates:
            return settings

        updated = await self._repo.update(settings, **updates)
        await self._session.commit()
        return updated
