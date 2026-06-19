from __future__ import annotations

from datetime import date

from app.services.us_market.base import UsMarketProvider
from app.services.us_market.schemas import UsMarketSnapshotData


class ManualUsMarketProvider(UsMarketProvider):
    """기본 provider. 외부 호출이 없으며 항상 None을 반환한다.

    "미국장 데이터는 사람이 직접 입력한다"는 현재 운영 방식을 그대로 표현한다.
    refresh 서비스는 None을 받으면 아무것도 덮어쓰지 않는다(no-op). API 키가 준비되어
    실제 벤더 어댑터를 붙이기 전까지의 안전한 기본값이다.
    """

    async def fetch_snapshot(
        self, session_date: date | None = None
    ) -> UsMarketSnapshotData | None:
        return None

    def provider_name(self) -> str:
        return "manual"
