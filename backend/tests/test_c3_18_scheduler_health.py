"""C-3.18 스케줄러 잡 건강 점검 테스트."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import SchedulerRunStatus
from app.domain.models.scheduler_run import SchedulerRun
from app.services.scheduler_health_service import SchedulerHealthService


class _Flags:
    """모든 잡 비활성 기본 + 지정 플래그만 True."""

    def __init__(self, **enabled):
        self._enabled = enabled

    def __getattr__(self, name):
        return self._enabled.get(name, False)


async def test_all_disabled_is_healthy(db_session: AsyncSession) -> None:
    out = await SchedulerHealthService(db_session).status()
    assert out["unhealthy_count"] == 0
    assert all(j["enabled"] is False for j in out["jobs"])


async def test_enabled_without_run_is_unhealthy(db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.scheduler_health_service.get_settings",
        lambda: _Flags(dart_ingest_scheduler_enabled=True),
    )
    out = await SchedulerHealthService(db_session).status()
    assert "dart_ingest" in out["unhealthy_jobs"]
    dart = next(j for j in out["jobs"] if j["job_id"] == "dart_ingest")
    assert dart["healthy"] is False and "실행 기록 없음" in dart["reason"]


async def test_recent_success_is_healthy(db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.scheduler_health_service.get_settings",
        lambda: _Flags(dart_ingest_scheduler_enabled=True),
    )
    db_session.add(SchedulerRun(
        job_id="dart_ingest", status=SchedulerRunStatus.SUCCESS,
        started_at=datetime.now(timezone.utc),
    ))
    await db_session.flush()
    out = await SchedulerHealthService(db_session).status()
    assert out["unhealthy_count"] == 0


async def test_last_failure_is_unhealthy(db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.scheduler_health_service.get_settings",
        lambda: _Flags(dart_ingest_scheduler_enabled=True),
    )
    db_session.add(SchedulerRun(
        job_id="dart_ingest", status=SchedulerRunStatus.FAILED,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        error_message="boom",
    ))
    await db_session.flush()
    out = await SchedulerHealthService(db_session).status()
    dart = next(j for j in out["jobs"] if j["job_id"] == "dart_ingest")
    assert dart["healthy"] is False and "실패" in dart["reason"]


async def test_unhealthy_job_appears_in_digest(db_session: AsyncSession, monkeypatch) -> None:
    """C-3.19: 활성인데 실행 기록 없는 잡은 다이제스트 경보로 잡힌다."""
    from app.services.operations_digest_service import OperationsDigestService

    monkeypatch.setattr(
        "app.services.scheduler_health_service.get_settings",
        lambda: _Flags(dart_ingest_scheduler_enabled=True),
    )
    digest = await OperationsDigestService(db_session).build()
    assert any("자율 잡 이상" in a["text"] for a in digest["alerts"])
