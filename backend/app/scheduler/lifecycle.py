import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from app.core.config import get_settings
from app.scheduler.jobs import run_strategy_job

logger = logging.getLogger(__name__)

STRATEGY_RUNNER_JOB_ID = "strategy_runner"


def start_scheduler(app: FastAPI) -> AsyncIOScheduler:
    """AsyncIOScheduler를 생성하고, 활성화 설정인 경우 전략 실행 작업을 등록 후 시작한다."""
    settings = get_settings()

    app.state.scheduler_last_run_at = None
    app.state.scheduler_last_error = None

    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

    if settings.strategy_scheduler_enabled:
        scheduler.add_job(
            run_strategy_job,
            trigger=IntervalTrigger(seconds=settings.strategy_scheduler_interval_seconds),
            id=STRATEGY_RUNNER_JOB_ID,
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
