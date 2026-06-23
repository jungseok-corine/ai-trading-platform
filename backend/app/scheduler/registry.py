"""자율(연구/분석) 잡 레지스트리 — 웹에서 ON/OFF 토글 가능한 잡 정의.

매매 인접 잡(strategy_runner/order_sync/trading_state_sync)은 여기 포함하지 않는다.
여기 있는 잡은 모두 read-only 연구/집계 잡이며 주문과 무관하다.
시작 시(lifecycle)와 런타임 토글(SchedulerControlService)이 이 레지스트리를 공유한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from app.scheduler.jobs import (
    DAILY_ANALYSIS_JOB_ID,
    DAILY_REPORT_JOB_ID,
    DART_FINANCE_JOB_ID,
    DART_INGEST_JOB_ID,
    DATA_REFRESH_JOB_ID,
    EDGAR_INGEST_JOB_ID,
    INTRADAY_EVENT_MONITOR_JOB_ID,
    OPERATIONS_DIGEST_JOB_ID,
    RESEARCH_PIPELINE_JOB_ID,
    SCANNER_REVIEW_JOB_ID,
    STRATEGY_REVIEW_JOB_ID,
    US_MARKET_REFRESH_JOB_ID,
    run_daily_analysis_job,
    run_daily_report_job,
    run_dart_finance_job,
    run_dart_ingest_job,
    run_data_refresh_job,
    run_edgar_ingest_job,
    run_intraday_event_monitor_job,
    run_operations_digest_job,
    run_research_pipeline_job,
    run_scanner_review_job,
    run_strategy_review_job,
    run_us_market_refresh_job,
)


@dataclass(frozen=True)
class ControllableJob:
    job_id: str
    label_ko: str
    schedule_desc: str
    func: Callable[[FastAPI], Awaitable[None]]
    build_trigger: Callable[[Any], Any]  # settings -> APScheduler trigger
    env_enabled: Callable[[Any], bool]  # settings -> env 기본 활성 여부


CONTROLLABLE_JOBS: list[ControllableJob] = [
    ControllableJob(
        job_id=RESEARCH_PIPELINE_JOB_ID,
        label_ko="연구 파이프라인 (스캔→후보→배정)",
        schedule_desc="5분 간격",
        func=run_research_pipeline_job,
        build_trigger=lambda s: IntervalTrigger(seconds=s.research_pipeline_interval_seconds),
        env_enabled=lambda s: s.research_pipeline_scheduler_enabled,
    ),
    ControllableJob(
        job_id=DATA_REFRESH_JOB_ID,
        label_ko="수급 데이터 수집",
        schedule_desc="매일 16:00",
        func=run_data_refresh_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.data_refresh_scheduler_hour, minute=s.data_refresh_scheduler_minute
        ),
        env_enabled=lambda s: s.data_refresh_scheduler_enabled,
    ),
    ControllableJob(
        job_id=US_MARKET_REFRESH_JOB_ID,
        label_ko="미국장 스냅샷 수집",
        schedule_desc="매일 07:00",
        func=run_us_market_refresh_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.us_market_refresh_scheduler_hour, minute=s.us_market_refresh_scheduler_minute
        ),
        env_enabled=lambda s: s.us_market_refresh_scheduler_enabled,
    ),
    ControllableJob(
        job_id=DAILY_ANALYSIS_JOB_ID,
        label_ko="AI 일일 분석 (LLM)",
        schedule_desc="매일 15:40",
        func=run_daily_analysis_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.ai_daily_analysis_scheduler_hour, minute=s.ai_daily_analysis_scheduler_minute
        ),
        env_enabled=lambda s: s.ai_daily_analysis_enabled,
    ),
    ControllableJob(
        job_id=SCANNER_REVIEW_JOB_ID,
        label_ko="스캐너 개선 제안 (검토)",
        schedule_desc="매일 16:10",
        func=run_scanner_review_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.scanner_review_scheduler_hour, minute=s.scanner_review_scheduler_minute
        ),
        env_enabled=lambda s: s.scanner_review_scheduler_enabled,
    ),
    ControllableJob(
        job_id=STRATEGY_REVIEW_JOB_ID,
        label_ko="전략 개선 제안 (검토)",
        schedule_desc="매일 16:20",
        func=run_strategy_review_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.strategy_review_scheduler_hour, minute=s.strategy_review_scheduler_minute
        ),
        env_enabled=lambda s: s.strategy_review_scheduler_enabled,
    ),
    ControllableJob(
        job_id=DAILY_REPORT_JOB_ID,
        label_ko="일일 리포트",
        schedule_desc="매일 15:45",
        func=run_daily_report_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.daily_report_scheduler_hour, minute=s.daily_report_scheduler_minute
        ),
        env_enabled=lambda s: s.daily_report_scheduler_enabled,
    ),
    ControllableJob(
        job_id=OPERATIONS_DIGEST_JOB_ID,
        label_ko="운영 다이제스트",
        schedule_desc="매일 16:30",
        func=run_operations_digest_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.operations_digest_scheduler_hour, minute=s.operations_digest_scheduler_minute
        ),
        env_enabled=lambda s: s.operations_digest_scheduler_enabled,
    ),
    ControllableJob(
        job_id=DART_INGEST_JOB_ID,
        label_ko="DART 공시 수집",
        schedule_desc="10분 간격",
        func=run_dart_ingest_job,
        build_trigger=lambda s: IntervalTrigger(seconds=s.dart_ingest_interval_seconds),
        env_enabled=lambda s: s.dart_ingest_scheduler_enabled,
    ),
    ControllableJob(
        job_id=EDGAR_INGEST_JOB_ID,
        label_ko="SEC EDGAR 공시 수집 (미국)",
        schedule_desc="30분 간격(미국장)",
        func=run_edgar_ingest_job,
        build_trigger=lambda s: IntervalTrigger(seconds=s.edgar_ingest_interval_seconds),
        env_enabled=lambda s: s.edgar_ingest_scheduler_enabled,
    ),
    ControllableJob(
        job_id=INTRADAY_EVENT_MONITOR_JOB_ID,
        label_ko="보유종목 장중 공시 감시",
        schedule_desc="10분 간격(장중)",
        func=run_intraday_event_monitor_job,
        build_trigger=lambda s: IntervalTrigger(
            seconds=s.intraday_event_monitor_interval_seconds
        ),
        env_enabled=lambda s: s.intraday_event_monitor_scheduler_enabled,
    ),
    ControllableJob(
        job_id=DART_FINANCE_JOB_ID,
        label_ko="DART 재무제표 수집 (XBRL)",
        schedule_desc="매일 02:00",
        func=run_dart_finance_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.dart_finance_scheduler_hour, minute=s.dart_finance_scheduler_minute
        ),
        env_enabled=lambda s: s.dart_finance_scheduler_enabled,
    ),
]

CONTROLLABLE_BY_ID: dict[str, ControllableJob] = {j.job_id: j for j in CONTROLLABLE_JOBS}


def apply_job_enabled(app: FastAPI, settings: Any, job: ControllableJob, enabled: bool) -> None:
    """실행 중인 scheduler에 잡을 추가/제거해 토글을 즉시 반영한다."""
    scheduler: AsyncIOScheduler | None = getattr(app.state, "scheduler", None)
    if scheduler is None:
        return
    existing = scheduler.get_job(job.job_id)
    if enabled and existing is None:
        scheduler.add_job(
            job.func,
            trigger=job.build_trigger(settings),
            id=job.job_id,
            args=[app],
            max_instances=1,
            replace_existing=True,
        )
    elif not enabled and existing is not None:
        scheduler.remove_job(job.job_id)
