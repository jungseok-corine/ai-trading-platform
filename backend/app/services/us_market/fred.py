from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from app.services.us_market.base import UsMarketProvider
from app.services.us_market.schemas import UsMarketProviderError, UsMarketSnapshotData

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# 우리 스냅샷 필드 ← FRED 시리즈 매핑.
#   레벨(value 그대로): VIX, 10년물 금리
#   % 변화(직전 거래일 대비): S&P500, 나스닥종합
SERIES_VIX = "VIXCLS"
SERIES_TREASURY_10Y = "DGS10"
SERIES_SP500 = "SP500"
SERIES_NASDAQ = "NASDAQCOM"

_MISSING = (None, "", ".")


def _numeric_values(observations: list[dict]) -> list[Decimal]:
    """observations(날짜 내림차순)에서 결측치(".")를 건너뛰고 Decimal 값만 추린다."""
    out: list[Decimal] = []
    for o in observations:
        v = o.get("value")
        if v in _MISSING:
            continue
        try:
            out.append(Decimal(str(v)))
        except (InvalidOperation, ValueError):
            continue
    return out


def latest_level(observations: list[dict]) -> Decimal | None:
    """가장 최근 유효 관측값(레벨)을 반환한다. VIX/금리용."""
    vals = _numeric_values(observations)
    return vals[0] if vals else None


def pct_change(observations: list[dict]) -> Decimal | None:
    """최근 2개 유효 관측값으로 직전 대비 % 변화를 계산한다. 지수 종가용."""
    vals = _numeric_values(observations)
    if len(vals) < 2 or vals[1] == 0:
        return None
    latest, prev = vals[0], vals[1]
    return (latest - prev) / prev * 100


def latest_obs_date(observations: list[dict]) -> date | None:
    for o in observations:
        if o.get("value") not in _MISSING:
            try:
                return date.fromisoformat(o["date"])
            except (ValueError, KeyError, TypeError):
                return None
    return None


class FredProvider(UsMarketProvider):
    """FRED(미 연준 세인트루이스)에서 미국장 매크로 스냅샷을 가져온다 (C-2.48).

    VIX/10년물 금리는 레벨로, S&P500/나스닥종합은 직전 거래일 대비 % 변화로 채운다.
    SOX는 FRED에 없으므로, sox_provider가 주어지면 거기서 보강한다(보통 Twelve Data).
    공식·무료 소스이며 주문과 무관한 read-only 수집이다.
    """

    def __init__(
        self,
        api_key: str | None,
        *,
        sox_provider: "UsMarketProvider | None" = None,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._sox_provider = sox_provider
        self._timeout = timeout_seconds
        self._client = client  # 테스트 주입용. None이면 요청 시 생성/정리.

    def provider_name(self) -> str:
        return "fred_twelvedata" if self._sox_provider is not None else "fred"

    async def _series(self, client: httpx.AsyncClient, series_id: str) -> list[dict]:
        resp = await client.get(
            FRED_BASE_URL,
            params={
                "series_id": series_id,
                "api_key": self._api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 5,
            },
        )
        resp.raise_for_status()
        return resp.json().get("observations", [])

    async def fetch_snapshot(
        self, session_date: date | None = None
    ) -> UsMarketSnapshotData | None:
        if not self._api_key:
            raise UsMarketProviderError("FRED_API_KEY is not set")

        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns_client = self._client is None
        try:
            sp = await self._series(client, SERIES_SP500)
            nq = await self._series(client, SERIES_NASDAQ)
            vix = await self._series(client, SERIES_VIX)
            dgs10 = await self._series(client, SERIES_TREASURY_10Y)
        except httpx.HTTPError as e:
            raise UsMarketProviderError(f"FRED request failed: {e}") from e
        finally:
            if owns_client:
                await client.aclose()

        snap_date = latest_obs_date(sp) or session_date or date.today()
        data = UsMarketSnapshotData(
            session_date=snap_date,
            sp500_change_pct=pct_change(sp),
            nasdaq_change_pct=pct_change(nq),
            vix=latest_level(vix),
            treasury_10y=latest_level(dgs10),
            data={"source": "fred"},
        )

        if self._sox_provider is not None:
            sox = await self._sox_provider.fetch_snapshot(snap_date)
            if sox is not None and sox.sox_change_pct is not None:
                data.sox_change_pct = sox.sox_change_pct
                data.data["sox_source"] = sox.data.get("source")
        return data
