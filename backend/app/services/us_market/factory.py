"""US Market Provider factory.

get_us_market_provider(name)으로 provider 이름을 받아 구현체를 반환한다.

구현 상태:
  "manual"       → ManualUsMarketProvider (항상 사용 가능, 네트워크 없음, 기본값)
  "alphavantage" → 미구현 (Alpha Vantage. ALPHAVANTAGE_API_KEY 필요)
  "finnhub"      → 미구현 (Finnhub. FINNHUB_API_KEY 필요)
  "twelvedata"   → 미구현 (Twelve Data. TWELVEDATA_API_KEY 필요)

벤더 어댑터는 API 키가 준비되면 base.UsMarketProvider를 상속해 추가한다.
"""
from __future__ import annotations

from app.services.us_market.base import UsMarketProvider
from app.services.us_market.manual import ManualUsMarketProvider

_SUPPORTED_PROVIDERS: frozenset[str] = frozenset(
    {"manual", "alphavantage", "finnhub", "twelvedata"}
)
_IMPLEMENTED_PROVIDERS: frozenset[str] = frozenset({"manual"})


class UnknownUsMarketProviderError(ValueError):
    """알 수 없는 provider 이름이 지정되었을 때 발생한다."""

    def __init__(self, provider_name: str) -> None:
        super().__init__(
            f"Unknown US market provider: '{provider_name}'. "
            f"Supported: {', '.join(sorted(_SUPPORTED_PROVIDERS))}."
        )
        self.provider_name = provider_name


class UsMarketProviderNotImplementedError(NotImplementedError):
    """알려진 provider이지만 아직 어댑터가 구현되지 않았을 때 발생한다(API 키 필요)."""

    def __init__(self, provider_name: str) -> None:
        super().__init__(
            f"US market provider '{provider_name}' is not yet implemented "
            f"(requires an API key and adapter). "
            f"Currently implemented: {', '.join(sorted(_IMPLEMENTED_PROVIDERS))}."
        )
        self.provider_name = provider_name


def get_us_market_provider(provider_name: str) -> UsMarketProvider:
    """provider_name에 해당하는 UsMarketProvider 구현체를 반환한다."""
    if provider_name not in _SUPPORTED_PROVIDERS:
        raise UnknownUsMarketProviderError(provider_name)
    if provider_name == "manual":
        return ManualUsMarketProvider()
    raise UsMarketProviderNotImplementedError(provider_name)
