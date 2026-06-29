"""M2.14O — FRED 5xx/transient hardening + API key 마스킹 (네트워크 없이 MockTransport).

실제 FRED API/실 키 미사용. 비밀이 예외/결과에 새지 않는지, 5xx가 잡 전체를 죽이지 않는지 검증.
거래/주문/스케줄러와 무관.
"""
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.us_market.fred as fred_mod
from app.services.news_context_service import NewsContextService
from app.services.us_market.fred import FredProvider, redact_api_key
from app.services.us_market.schemas import UsMarketProviderError
from app.services.us_market_refresh_service import UsMarketRefreshService

FAKE_KEY = "FAKE_TEST_KEY_DO_NOT_USE"


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    async def _no_sleep(_):
        return None
    monkeypatch.setattr(fred_mod.asyncio, "sleep", _no_sleep)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --- redaction ---------------------------------------------------------------
def test_redact_masks_api_key():
    raw = f"https://api.stlouisfed.org/fred/series/observations?series_id=SP500&api_key={FAKE_KEY}&file_type=json"
    out = redact_api_key(raw)
    assert FAKE_KEY not in out
    assert "api_key=***REDACTED***" in out
    assert "series_id=SP500" in out  # 다른 파라미터는 유지


# --- 5xx transient -----------------------------------------------------------
async def test_fred_500_raises_transient_without_key():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="Server error")

    provider = FredProvider(FAKE_KEY, client=_client(handler))
    with pytest.raises(UsMarketProviderError) as ei:
        await provider.fetch_snapshot()
    err = ei.value
    assert err.transient is True
    assert FAKE_KEY not in str(err)  # 키가 메시지에 새면 안 됨
    assert calls["n"] == 3  # bounded 재시도(1 + 2)


async def test_fred_429_is_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    with pytest.raises(UsMarketProviderError) as ei:
        await FredProvider(FAKE_KEY, client=_client(handler)).fetch_snapshot()
    assert ei.value.transient is True
    assert FAKE_KEY not in str(ei.value)


async def test_fred_timeout_is_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(UsMarketProviderError) as ei:
        await FredProvider(FAKE_KEY, client=_client(handler)).fetch_snapshot()
    assert ei.value.transient is True
    assert FAKE_KEY not in str(ei.value)


# --- 4xx client/auth ---------------------------------------------------------
async def test_fred_4xx_is_not_transient_no_retry_no_key():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, text="forbidden")

    with pytest.raises(UsMarketProviderError) as ei:
        await FredProvider(FAKE_KEY, client=_client(handler)).fetch_snapshot()
    assert ei.value.transient is False
    assert calls["n"] == 1  # 4xx는 재시도 안 함
    assert FAKE_KEY not in str(ei.value)
    assert "403" in str(ei.value)


async def test_missing_key_raises_not_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"observations": []})

    with pytest.raises(UsMarketProviderError) as ei:
        await FredProvider(None, client=_client(handler)).fetch_snapshot()
    assert ei.value.transient is False
    assert FAKE_KEY not in str(ei.value)


# --- observations edge cases -------------------------------------------------
async def test_missing_and_empty_observations_handled():
    obs = {
        "SP500": [{"date": "2026-06-26", "value": "."}, {"date": "2026-06-25", "value": "5000"},
                  {"date": "2026-06-24", "value": "4950"}],
        "NASDAQCOM": [],  # empty
    }

    def handler(request: httpx.Request) -> httpx.Response:
        sid = dict(httpx.QueryParams(request.url.query.decode()))["series_id"]
        return httpx.Response(200, json={"observations": obs.get(sid, [{"date": "2026-06-26", "value": "1.5"}])})

    data = await FredProvider(FAKE_KEY, client=_client(handler)).fetch_snapshot()
    assert data is not None
    assert data.sp500_change_pct is not None  # "." 건너뛰고 5000/4950로 계산
    assert data.nasdaq_change_pct is None  # empty → None


# --- refresh service degraded behavior ---------------------------------------
async def test_refresh_degrades_on_500_preserves_stale_cache(db_session: AsyncSession):
    # 기존 캐시 스냅샷 seed
    news = NewsContextService(db_session)
    await news.upsert_us_snapshot(date(2026, 6, 20), sp500_change_pct=Decimal("1.23"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Server error")

    provider = FredProvider(FAKE_KEY, client=_client(handler))
    result = await UsMarketRefreshService(db_session, provider=provider).refresh()

    assert result.updated is False
    assert result.degraded is True
    assert result.transient is True
    assert FAKE_KEY not in (result.reason or "")
    assert result.stale_session_date == date(2026, 6, 20)
    # 기존 캐시 보존(덮어쓰지 않음)
    stale = await news.get_latest_us_snapshot()
    assert stale is not None and stale.sp500_change_pct == Decimal("1.23")


async def test_refresh_degrades_when_no_cache(db_session: AsyncSession):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    result = await UsMarketRefreshService(
        db_session, provider=FredProvider(FAKE_KEY, client=_client(handler))
    ).refresh()
    assert result.updated is False and result.degraded is True
    assert result.stale_session_date is None
    assert FAKE_KEY not in (result.reason or "")


async def test_refresh_success_still_upserts(db_session: AsyncSession):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"observations": [
            {"date": "2026-06-26", "value": "5000"}, {"date": "2026-06-25", "value": "4950"}]})

    result = await UsMarketRefreshService(
        db_session, provider=FredProvider(FAKE_KEY, client=_client(handler))
    ).refresh()
    assert result.updated is True and result.degraded is False
