import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


@pytest_asyncio.fixture
async def db_session():
    """각 테스트를 별도 트랜잭션으로 격리하고, 종료 시 롤백한다.

    엔진을 테스트마다 새로 생성하는 이유: pytest-asyncio가 테스트별로 새
    이벤트 루프를 만들 수 있는데, 모듈 전역 엔진의 커넥션 풀을 재사용하면
    이전 루프에 묶인 asyncpg 커넥션을 사용하게 되어 오류가 발생한다.
    """
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session_factory = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with session_factory() as session:
            yield session
        await trans.rollback()
    await engine.dispose()
