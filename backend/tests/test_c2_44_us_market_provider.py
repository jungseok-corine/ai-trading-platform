"""C-2.44 미국장 데이터 provider 추상화 + refresh 서비스 테스트."""

from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.services.us_market import (
    UnknownUsMarketProviderError,
    UsMarketProviderNotImplementedError,
    UsMarketSnapshotData,
    get_us_market_provider,
)
from app.services.us_market.base import UsMarketProvider
from app.services.us_market_refresh_service import UsMarketRefreshService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


class _FakeProvider(UsMarketProvider):
    """테스트용 provider: 고정된 스냅샷 데이터를 반환한다."""

    def __init__(self, data: UsMarketSnapshotData | None) -> None:
        self._data = data

    async def fetch_snapshot(self, session_date=None):
        return self._data

    def provider_name(self) -> str:
        return "fake"


# --- factory ----------------------------------------------------------------
def test_factory_manual_is_default_and_noop() -> None:
    provider = get_us_market_provider("manual")
    assert provider.provider_name() == "manual"


def test_factory_unknown_provider_raises() -> None:
    with pytest.raises(UnknownUsMarketProviderError):
        get_us_market_provider("bogus")


def test_factory_known_but_unimplemented_raises() -> None:
    with pytest.raises(UsMarketProviderNotImplementedError):
        get_us_market_provider("alphavantage")


async def test_manual_provider_returns_none() -> None:
    provider = get_us_market_provider("manual")
    assert await provider.fetch_snapshot() is None


# --- refresh service --------------------------------------------------------
async def test_refresh_manual_is_noop(db_session: AsyncSession) -> None:
    service = UsMarketRefreshService(db_session, provider=get_us_market_provider("manual"))
    result = await service.refresh()
    assert result.updated is False
    assert result.provider == "manual"
    # 아무 스냅샷도 생성되지 않는다.
    assert await service.latest() is None


async def test_refresh_with_provider_upserts(db_session: AsyncSession) -> None:
    data = UsMarketSnapshotData(
        session_date=date(2026, 6, 18),
        nasdaq_change_pct=Decimal("1.2"),
        sox_change_pct=Decimal("2.5"),
        major_news=["AI rally"],
    )
    service = UsMarketRefreshService(db_session, provider=_FakeProvider(data))
    result = await service.refresh()

    assert result.updated is True
    assert result.session_date == date(2026, 6, 18)
    latest = await service.latest()
    assert latest is not None
    assert latest.nasdaq_change_pct == Decimal("1.2000")
    assert latest.major_news == ["AI rally"]


async def test_refresh_is_idempotent_per_date(db_session: AsyncSession) -> None:
    data = UsMarketSnapshotData(session_date=date(2026, 6, 18), vix=Decimal("15"))
    service = UsMarketRefreshService(db_session, provider=_FakeProvider(data))
    await service.refresh()
    await service.refresh()  # 같은 날짜 → 갱신(중복 생성 없음)
    snaps = await service._news_service.list_us_snapshots()
    same = [s for s in snaps if s.session_date == date(2026, 6, 18)]
    assert len(same) == 1


async def test_refresh_via_api_manual(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/us-market-snapshots/refresh")
            assert resp.status_code == 200
            body = resp.json()
            assert body["provider"] == "manual"
            assert body["updated"] is False
    finally:
        app.dependency_overrides.clear()
