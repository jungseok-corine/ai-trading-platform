"""C-3.9 운영 다이제스트 스케줄러 잡 테스트."""

import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.scheduler.jobs import run_operations_digest_job


@pytest_asyncio.fixture
async def job_session_factory(monkeypatch):
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("app.scheduler.jobs.async_session_factory", factory)
    yield factory
    await engine.dispose()


async def test_digest_job_runs_without_error(job_session_factory) -> None:
    app = FastAPI()
    app.state.operations_digest_last_run_at = None
    app.state.operations_digest_last_error = None

    await run_operations_digest_job(app)

    # 기본 채널 none + 데이터 없음 → 오류 없이 완료
    assert app.state.operations_digest_last_error is None
    assert app.state.operations_digest_last_run_at is not None
