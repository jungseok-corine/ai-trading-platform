"""us_market 패키지 공개 API.

미국장 일별 스냅샷(나스닥/S&P500/SOX/금리/VIX)을 외부 소스에서 가져오는 provider 추상화.
AI provider(ai_analysis)와 동일한 패턴: ABC 계약 + 구현체 + factory.

    from app.services.us_market import get_us_market_provider, UsMarketSnapshotData

기본 provider는 "manual" — 네트워크 호출이 없고, 사람이 직접 입력한 스냅샷을 그대로 둔다.
실제 벤더(alphavantage/finnhub/twelvedata) 어댑터는 API 키가 준비되면 붙인다.
"""
from app.services.us_market.base import UsMarketProvider
from app.services.us_market.factory import (
    UnknownUsMarketProviderError,
    UsMarketProviderNotImplementedError,
    get_us_market_provider,
)
from app.services.us_market.schemas import UsMarketProviderError, UsMarketSnapshotData

__all__ = [
    "UsMarketProvider",
    "UsMarketProviderError",
    "UsMarketProviderNotImplementedError",
    "UsMarketSnapshotData",
    "UnknownUsMarketProviderError",
    "get_us_market_provider",
]
