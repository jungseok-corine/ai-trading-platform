from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.services.us_market.schemas import UsMarketSnapshotData


class UsMarketProvider(ABC):
    """미국장 일별 스냅샷 provider 공통 인터페이스.

    각 구현체는 이 클래스를 상속하고 fetch_snapshot()을 구현한다. 호출자(refresh 서비스)는
    구체 provider를 알 필요 없이 이 인터페이스만 사용한다.
    """

    @abstractmethod
    async def fetch_snapshot(
        self, session_date: date | None = None
    ) -> UsMarketSnapshotData | None:
        """session_date(미지정 시 직전 거래일)의 미국장 스냅샷을 가져온다.

        Returns:
            UsMarketSnapshotData, 또는 None(데이터를 제공하지 않는 provider).

        Raises:
            UsMarketProviderError: 조회 실패(네트워크/인증/rate limit 등).
        """
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """이 provider의 식별자. 예: "manual", "alphavantage"."""
        ...
