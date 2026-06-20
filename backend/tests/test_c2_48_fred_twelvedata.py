"""C-2.48 FRED + Twelve Data 미국장 provider 테스트 (네트워크 없이 MockTransport)."""

from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.us_market import UsMarketProviderError, get_us_market_provider
from app.services.us_market.fred import (
    FredProvider,
    latest_level,
    latest_obs_date,
    pct_change,
)
from app.services.us_market.twelvedata import TwelveDataProvider, parse_percent_change
from app.services.us_market_refresh_service import UsMarketRefreshService

FRED_FIXTURES = {
    "SP500": [
        {"date": "2026-06-19", "value": "5050"},
        {"date": "2026-06-18", "value": "5000"},
    ],
    "NASDAQCOM": [
        {"date": "2026-06-19", "value": "18180"},
        {"date": "2026-06-18", "value": "18000"},
    ],
    # 결측치(".")가 섞여도 최신 유효값을 집는다.
    "VIXCLS": [
        {"date": "2026-06-19", "value": "15.5"},
        {"date": "2026-06-18", "value": "."},
    ],
    "DGS10": [{"date": "2026-06-19", "value": "4.25"}],
}


def _mock_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "stlouisfed.org" in url:
        series = request.url.params.get("series_id")
        return httpx.Response(200, json={"observations": FRED_FIXTURES.get(series, [])})
    if "twelvedata.com" in url:
        return httpx.Response(200, json={"symbol": "SOXX", "percent_change": "2.5"})
    return httpx.Response(404)


def _mock_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(_mock_handler))


# --- 순수 파서 --------------------------------------------------------------
def test_pct_change_uses_latest_two() -> None:
    assert pct_change(FRED_FIXTURES["SP500"]) == Decimal("1")


def test_pct_change_none_when_insufficient() -> None:
    assert pct_change([{"date": "d", "value": "100"}]) is None
    assert pct_change([{"date": "d", "value": "."}, {"date": "e", "value": "."}]) is None


def test_latest_level_skips_missing() -> None:
    assert latest_level(FRED_FIXTURES["VIXCLS"]) == Decimal("15.5")
    assert latest_level([{"date": "d", "value": "."}]) is None


def test_latest_obs_date() -> None:
    assert latest_obs_date(FRED_FIXTURES["SP500"]) == date(2026, 6, 19)


def test_twelvedata_parse() -> None:
    assert parse_percent_change({"percent_change": "2.5"}) == Decimal("2.5")
    assert parse_percent_change({"percent_change": ""}) is None
    with pytest.raises(UsMarketProviderError):
        parse_percent_change({"status": "error", "message": "bad key"})


# --- provider (MockTransport) ----------------------------------------------
async def test_fred_provider_fetches_macro() -> None:
    provider = FredProvider("fake-key", client=_mock_client())
    data = await provider.fetch_snapshot()
    assert provider.provider_name() == "fred"
    assert data is not None
    assert data.session_date == date(2026, 6, 19)
    assert data.sp500_change_pct == Decimal("1")
    assert data.nasdaq_change_pct == Decimal("1")
    assert data.vix == Decimal("15.5")
    assert data.treasury_10y == Decimal("4.25")
    assert data.sox_change_pct is None  # FRED 단독은 SOX 없음


async def test_fred_with_twelvedata_sox() -> None:
    sox = TwelveDataProvider("td-key", client=_mock_client())
    provider = FredProvider("fred-key", sox_provider=sox, client=_mock_client())
    data = await provider.fetch_snapshot()
    assert provider.provider_name() == "fred_twelvedata"
    assert data.sox_change_pct == Decimal("2.5")
    assert data.data["sox_source"] == "twelvedata"


async def test_missing_key_raises() -> None:
    with pytest.raises(UsMarketProviderError):
        await FredProvider(None, client=_mock_client()).fetch_snapshot()
    with pytest.raises(UsMarketProviderError):
        await TwelveDataProvider(None, client=_mock_client()).fetch_snapshot()


# --- factory ----------------------------------------------------------------
def test_factory_builds_implemented_providers() -> None:
    assert get_us_market_provider("fred").provider_name() == "fred"
    assert get_us_market_provider("twelvedata").provider_name() == "twelvedata"
    assert get_us_market_provider("fred_twelvedata").provider_name() == "fred_twelvedata"


# --- refresh service end-to-end --------------------------------------------
async def test_refresh_upserts_from_fred(db_session: AsyncSession) -> None:
    sox = TwelveDataProvider("td-key", client=_mock_client())
    provider = FredProvider("fred-key", sox_provider=sox, client=_mock_client())
    service = UsMarketRefreshService(db_session, provider=provider)

    result = await service.refresh()
    assert result.updated is True
    assert result.provider == "fred_twelvedata"

    latest = await service.latest()
    assert latest is not None
    assert latest.session_date == date(2026, 6, 19)
    assert latest.vix == Decimal("15.5000")
    assert latest.treasury_10y == Decimal("4.2500")
    assert latest.sp500_change_pct == Decimal("1.0000")
    assert latest.sox_change_pct == Decimal("2.5000")
