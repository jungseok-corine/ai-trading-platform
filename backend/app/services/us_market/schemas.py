from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


class UsMarketProviderError(Exception):
    """미국장 데이터 조회 실패(네트워크/인증/rate limit 등)."""


@dataclass
class UsMarketSnapshotData:
    """provider가 반환하는 미국장 일별 스냅샷 데이터(저장 전 표현).

    값은 Decimal | None. None은 '해당 지표를 제공하지 않음'을 의미한다.
    """

    session_date: date
    nasdaq_change_pct: Decimal | None = None
    sp500_change_pct: Decimal | None = None
    sox_change_pct: Decimal | None = None
    treasury_10y: Decimal | None = None
    vix: Decimal | None = None
    major_news: list | None = None
    data: dict = field(default_factory=dict)

    def to_upsert_fields(self) -> dict:
        """NewsContextService.upsert_us_snapshot(**fields)에 넘길 dict로 변환한다."""
        return {
            "nasdaq_change_pct": self.nasdaq_change_pct,
            "sp500_change_pct": self.sp500_change_pct,
            "sox_change_pct": self.sox_change_pct,
            "treasury_10y": self.treasury_10y,
            "vix": self.vix,
            "major_news": self.major_news,
            "data": self.data,
        }
