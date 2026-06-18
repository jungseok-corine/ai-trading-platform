import os
from pathlib import Path

# 다른 app.* 모듈이 import되기 전에 DATABASE_URL을 테스트 전용 DB로 덮어쓴다.
# app.db.session, alembic/env.py 등은 모듈 임포트 시점에 get_settings().database_url로
# 엔진을 생성하므로, 이 override는 반드시 다른 app.* import보다 먼저 실행되어야 한다.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://trading:trading@localhost:5432/trading_platform_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

get_settings.cache_clear()

ALEMBIC_INI_PATH = Path(__file__).resolve().parent.parent / "alembic.ini"


def _require_test_database(database_url: str) -> str:
    """dev DB(trading_platform)를 실수로 사용하지 않도록 DB 이름을 검증한다."""
    db_name = database_url.rsplit("/", 1)[-1]
    if db_name == "trading_platform":
        raise RuntimeError(
            "테스트가 dev DB(trading_platform)를 가리키고 있습니다. "
            "TEST_DATABASE_URL을 trading_platform_test 등 별도 DB로 설정하세요."
        )
    return db_name


async def _ensure_database_exists(database_url: str, db_name: str) -> None:
    """테스트 DB가 없으면 생성한다 (dev DB의 데이터는 건드리지 않음)."""
    admin_url = database_url.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_async_engine(admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            exists = await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name})
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        await admin_engine.dispose()


def _upgrade_to_head() -> None:
    """테스트 DB에 alembic 마이그레이션을 최신 상태로 적용한다."""
    config = Config(str(ALEMBIC_INI_PATH))
    command.upgrade(config, "head")


async def _truncate_all_tables(database_url: str) -> None:
    """테스트 DB의 모든 데이터 테이블을 비운다.

    alembic_version은 제외한다. RESTART IDENTITY로 시퀀스도 초기화한다.
    이전 pytest 세션에서 남은 잔여 데이터를 제거해 테스트 격리를 보장한다.
    """
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename != 'alembic_version'"
                "ORDER BY tablename"
            ))
            tables = [row[0] for row in result.fetchall()]
            if tables:
                table_list = ", ".join(f'"{t}"' for t in tables)
                await conn.execute(text(
                    f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"
                ))
            await conn.commit()
    finally:
        await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    """세션 시작 시 1회: 테스트 DB(trading_platform_test)를 생성하고 스키마를 최신화한다.

    모든 데이터 테이블을 비워 이전 세션 잔여 데이터로 인한 테스트 오염을 방지한다.
    dev DB(trading_platform)의 strategies/trades/signal_logs/scheduler_runs 등은
    전혀 조회·수정하지 않는다.
    """
    import asyncio

    settings = get_settings()
    db_name = _require_test_database(settings.database_url)
    asyncio.run(_ensure_database_exists(settings.database_url, db_name))
    _upgrade_to_head()
    asyncio.run(_truncate_all_tables(settings.database_url))


@pytest_asyncio.fixture
async def db_session(_prepare_test_database):
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


@pytest_asyncio.fixture
async def db_session_with_factory(_prepare_test_database):
    """(session, factory) 튜플을 반환한다. persistence 테스트 전용.

    factory로 추가 session을 생성하면 같은 connection 위에서
    새로운 identity map으로 데이터를 조회할 수 있다.

    service.commit() → savepoint release → 같은 connection의 다른 session에서 조회 가능
    → flush만 된 상태(미커밋)와 commit된 상태를 구분하는 테스트에 사용한다.
    """
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        trans = await conn.begin()
        factory = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with factory() as session:
            yield session, factory
        await trans.rollback()
    await engine.dispose()
