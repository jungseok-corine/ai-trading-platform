"""C-4.7 자율 잡 제어판: DB 오버라이드 영속 + 실효 활성 + 토글."""
import types

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.scheduler.registry import CONTROLLABLE_JOBS
from app.services.scheduler_control_service import SchedulerControlService, UnknownJobError


def _fake_app() -> types.SimpleNamespace:
    # app.state.scheduler 없음 → apply_job_enabled는 no-op(런타임 스케줄러 없을 때 안전)
    return types.SimpleNamespace(state=types.SimpleNamespace())


async def test_effective_defaults_follow_env_when_no_override(db_session: AsyncSession) -> None:
    settings = get_settings()
    eff = await SchedulerControlService(db_session).effective_enabled_map(settings)
    assert set(eff.keys()) == {j.job_id for j in CONTROLLABLE_JOBS}
    # 오버라이드 없으면 env 기본값을 그대로 따른다(안전 불변식: 임의 자동 활성 없음).
    for j in CONTROLLABLE_JOBS:
        assert eff[j.job_id] == j.env_enabled(settings)


async def test_set_enabled_persists_and_overrides_env(db_session: AsyncSession) -> None:
    settings = get_settings()
    service = SchedulerControlService(db_session)
    app = _fake_app()

    await service.set_enabled("research_pipeline", True, app, settings)
    eff = await service.effective_enabled_map(settings)
    assert eff["research_pipeline"] is True

    await service.set_enabled("research_pipeline", False, app, settings)
    eff = await service.effective_enabled_map(settings)
    assert eff["research_pipeline"] is False


async def test_list_jobs_marks_overridden(db_session: AsyncSession) -> None:
    settings = get_settings()
    service = SchedulerControlService(db_session)
    app = _fake_app()

    await service.set_enabled("daily_report", True, app, settings)
    jobs = await service.list_jobs(app, settings)

    dr = next(j for j in jobs if j.job_id == "daily_report")
    assert dr.enabled is True and dr.overridden is True and dr.running is False
    rp = next(j for j in jobs if j.job_id == "research_pipeline")
    assert rp.overridden is False  # 토글 안 한 잡은 env 기본값


async def test_unknown_job_raises(db_session: AsyncSession) -> None:
    service = SchedulerControlService(db_session)
    with pytest.raises(UnknownJobError):
        await service.set_enabled("not_a_job", True, _fake_app(), get_settings())
    with pytest.raises(UnknownJobError):
        await service.run_now("not_a_job", _fake_app())
