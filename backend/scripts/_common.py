"""운영 스크립트 공통 헬퍼.

여러 일회성 스크립트가 공유하던 DB 세션 + engine dispose 보일러플레이트를 한 곳에 모은다.
경로/.env 부트스트랩은 app import보다 먼저 실행돼야 하므로 각 스크립트 상단에 인라인으로 둔다.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def db_session() -> AsyncIterator[AsyncSession]:
    """async DB 세션을 열고, 종료 시 engine을 dispose한다.

    사용:
        async with db_session() as session:
            await run(session, ...)
    """
    from app.db.session import async_session_factory, engine

    try:
        async with async_session_factory() as session:
            yield session
    finally:
        await engine.dispose()
