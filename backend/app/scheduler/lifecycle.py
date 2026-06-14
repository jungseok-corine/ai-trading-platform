import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.scheduler.jobs import ORDER_SYNC_JOB_ID, STRATEGY_RUNNER_JOB_ID, order_sync_job, run_strategy_job
from app.services.scheduler_settings_service import SchedulerSettingsService

logger = logging.getLogger(__name__)


async def _load_scheduler_intervals() -> tuple[int, int]:
    """DB에 저장된 스케줄러 주기 설정을 읽는다 (없으면 config 기본값으로 생성)."""
    async with async_session_factory() as session:
        settings = await SchedulerSettingsService(session).get_settings()
        return settings.strategy_scheduler_interval_seconds, settings.order_sync_scheduler_interval_seconds


async def start_scheduler(app: FastAPI) -> AsyncIOScheduler:
    """AsyncIOScheduler를 생성하고, 활성화 설정인 경우 전략 실행/주문 동기화 작업을 등록 후 시작한다.

    작업 주기는 DB(scheduler_settings)에 저장된 값을 우선 사용하며, 저장된 값이 없으면
    app.core.config의 기본값으로 singleton row를 생성한다.
    """
    settings = get_settings()
    strategy_interval, order_sync_interval = await _load_scheduler_intervals()

    app.state.scheduler_last_run_at = None
    app.state.scheduler_last_error = None
    app.state.scheduler_last_error_category = None
    app.state.order_sync_last_run_at = None
    app.state.order_sync_last_error = None
    app.state.order_sync_last_error_category = None

    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

    if settings.strategy_scheduler_enabled:
        scheduler.add_job(
            run_strategy_job,
            trigger=IntervalTrigger(seconds=strategy_interval),
            id=STRATEGY_RUNNER_JOB_ID,
            args=[app],
            max_instances=1,
            replace_existing=True,
        )

    if settings.order_sync_scheduler_enabled:
        scheduler.add_job(
            order_sync_job,
            trigger=IntervalTrigger(seconds=order_sync_interval),
            id=ORDER_SYNC_JOB_ID,
            args=[app],
            max_instances=1,
            replace_existing=True,
        )

    scheduler.start()
    app.state.scheduler = scheduler
    return scheduler


def shutdown_scheduler(app: FastAPI) -> None:
    """서버 종료 시 scheduler를 정상적으로 종료한다."""
    scheduler: AsyncIOScheduler | None = getattr(app.state, "scheduler", None)
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)


def reschedule_jobs(
    app: FastAPI,
    strategy_scheduler_interval_seconds: int | None = None,
    order_sync_scheduler_interval_seconds: int | None = None,
) -> None:
    """실행 중인 scheduler job의 주기를 변경한다 (해당 job이 등록되어 있는 경우에만)."""
    scheduler: AsyncIOScheduler | None = getattr(app.state, "scheduler", None)
    if scheduler is None:
        return

    if strategy_scheduler_interval_seconds is not None and scheduler.get_job(STRATEGY_RUNNER_JOB_ID) is not None:
        scheduler.reschedule_job(
            STRATEGY_RUNNER_JOB_ID, trigger=IntervalTrigger(seconds=strategy_scheduler_interval_seconds)
        )

    if order_sync_scheduler_interval_seconds is not None and scheduler.get_job(ORDER_SYNC_JOB_ID) is not None:
        scheduler.reschedule_job(
            ORDER_SYNC_JOB_ID, trigger=IntervalTrigger(seconds=order_sync_scheduler_interval_seconds)
        )
