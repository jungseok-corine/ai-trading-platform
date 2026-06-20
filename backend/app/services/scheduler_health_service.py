from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.enums import SchedulerRunStatus
from app.domain.repositories.scheduler_run import SchedulerRunRepository

# 자율 잡: (job_id, config의 enabled 플래그명, 마지막 실행이 stale로 간주되는 시간).
# 잡이 비활성이면 점검 대상이 아니다(정상). 활성인데 오래 안 돌거나 마지막이 실패면 경고.
_JOBS = [
    ("research_pipeline", "research_pipeline_scheduler_enabled", 6),
    ("scanner_review", "scanner_review_scheduler_enabled", 48),
    ("strategy_review", "strategy_review_scheduler_enabled", 48),
    ("daily_report", "daily_report_scheduler_enabled", 48),
    ("data_refresh", "data_refresh_scheduler_enabled", 48),
    ("us_market_refresh", "us_market_refresh_scheduler_enabled", 48),
    ("dart_ingest", "dart_ingest_scheduler_enabled", 6),
    ("daily_analysis", "ai_daily_analysis_enabled", 48),
    ("operations_digest", "operations_digest_scheduler_enabled", 48),
]


class SchedulerHealthService:
    """자율 스케줄러 잡 건강 점검 (C-3.18).

    설정상 '활성'인 잡이 실제로 최근에 돌았는지, 마지막 실행이 실패하지 않았는지 점검한다.
    비활성 잡은 점검 대상이 아니다(끈 것은 정상). read-only 점검 — 아무것도 바꾸지 않는다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = SchedulerRunRepository(session)

    async def status(self) -> dict:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        jobs: list[dict] = []
        unhealthy = 0
        for job_id, flag, stale_hours in _JOBS:
            enabled = bool(getattr(settings, flag, False))
            run = await self._repo.latest_by_job(job_id)
            last_at = run.started_at if run else None
            last_status = run.status.value if run else None
            age_hours = None
            healthy = True
            reason = None
            if enabled:
                if run is None:
                    healthy, reason = False, "활성이나 실행 기록 없음"
                else:
                    if last_at.tzinfo is None:
                        last_at = last_at.replace(tzinfo=timezone.utc)
                    age_hours = round((now - last_at).total_seconds() / 3600, 1)
                    if run.status == SchedulerRunStatus.FAILED:
                        healthy, reason = False, "마지막 실행 실패"
                    elif age_hours > stale_hours:
                        healthy, reason = False, f"{stale_hours}h 이상 미실행"
            if enabled and not healthy:
                unhealthy += 1
            jobs.append({
                "job_id": job_id,
                "enabled": enabled,
                "last_run_at": last_at.isoformat() if last_at else None,
                "last_status": last_status,
                "age_hours": age_hours,
                "stale_hours": stale_hours,
                "healthy": healthy,
                "reason": reason,
            })
        return {
            "checked_at": now.isoformat(),
            "unhealthy_count": unhealthy,
            "unhealthy_jobs": [j["job_id"] for j in jobs if j["enabled"] and not j["healthy"]],
            "jobs": jobs,
        }
