from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from app.services.us_market.base import UsMarketProvider
from app.services.us_market.schemas import UsMarketProviderError, UsMarketSnapshotData

TWELVEDATA_QUOTE_URL = "https://api.twelvedata.com/quote"

_MISSING = (None, "")


def parse_percent_change(body: dict) -> Decimal | None:
    """Twelve Data /quote 응답에서 percent_change를 Decimal로 파싱한다.

    오류 응답(status="error")은 UsMarketProviderError로 올린다.
    """
    if body.get("status") == "error":
        raise UsMarketProviderError(
            f"twelvedata error: {body.get('message', 'unknown')}"
        )
    pc = body.get("percent_change")
    if pc in _MISSING:
        return None
    try:
        return Decimal(str(pc))
    except (InvalidOperation, ValueError):
        return None


class TwelveDataProvider(UsMarketProvider):
    """Twelve Data에서 SOX(기본 SOXX ETF proxy)의 일간 % 변화를 가져온다 (C-2.48).

    SOX 지수 자체는 라이선스 제약이 있어 기본 심볼은 SOXX(iShares 반도체 ETF)로 둔다.
    단독으로 쓰면 sox_change_pct만 채운 스냅샷을 반환하고, FredProvider의 sox_provider로
    주입되면 SOX 보강 용도로 쓰인다. read-only 수집이며 주문과 무관하다.
    """

    def __init__(
        self,
        api_key: str | None,
        *,
        symbol: str = "SOXX",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._symbol = symbol
        self._timeout = timeout_seconds
        self._client = client

    def provider_name(self) -> str:
        return "twelvedata"

    async def fetch_snapshot(
        self, session_date: date | None = None
    ) -> UsMarketSnapshotData | None:
        if not self._api_key:
            raise UsMarketProviderError("TWELVEDATA_API_KEY is not set")

        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns_client = self._client is None
        try:
            resp = await client.get(
                TWELVEDATA_QUOTE_URL,
                params={"symbol": self._symbol, "apikey": self._api_key},
            )
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as e:
            raise UsMarketProviderError(f"twelvedata request failed: {e}") from e
        finally:
            if owns_client:
                await client.aclose()

        return UsMarketSnapshotData(
            session_date=session_date or date.today(),
            sox_change_pct=parse_percent_change(body),
            data={"source": "twelvedata", "symbol": self._symbol},
        )
