from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.watchlist import Watchlist, WatchlistSymbol
from app.services.investor_flow_service import InvestorFlowService

KST = ZoneInfo("Asia/Seoul")


@dataclass
class RefreshSummary:
    """수급 데이터 새로고침 1회 결과."""

    requested: int
    succeeded: int
    failed: int
    rows: int
    errors: dict[str, str] = field(default_factory=dict)


class DataRefreshService:
    """watchlist 종목의 수급 데이터를 KIS에서 가져와 DB에 채운다 (C-2.34).

    스캐너/전략이 신선한 수급 데이터를 쓸 수 있도록 "엮는" 단계다. 실제 수집은 주입된
    InvestorFlowService(KIS 클라이언트 포함)가 담당하며, 종목별 실패는 격리되어 전체를
    중단시키지 않는다. KIS 호출은 read-only이며 주문과 무관하다.
    """

    def __init__(self, session: AsyncSession, flow_service: InvestorFlowService) -> None:
        self._session = session
        self._flow_service = flow_service

    async def watchlist_symbols(self) -> list[str]:
        """enabled watchlist에 속한 enabled 종목 코드 목록(중복 제거)을 반환한다."""
        result = await self._session.execute(
            select(WatchlistSymbol.symbol_code)
            .join(Watchlist, Watchlist.id == WatchlistSymbol.watchlist_id)
            .where(Watchlist.enabled.is_(True), WatchlistSymbol.enabled.is_(True))
            .distinct()
        )
        return [row[0] for row in result.all()]

    async def refresh_investor_flows(
        self,
        symbol_codes: list[str],
        date_from: date | None = None,
        date_to: date | None = None,
        lookback_days: int = 5,
    ) -> RefreshSummary:
        """종목별로 date_from~date_to 수급 데이터를 가져와 저장한다.

        날짜 미지정 시 최근 lookback_days일을 사용한다. 종목별 예외는 errors에 모으고 계속 진행한다.
        """
        if date_to is None:
            date_to = datetime.now(KST).date()
        if date_from is None:
            date_from = date_to - timedelta(days=lookback_days)

        succeeded = 0
        failed = 0
        total_rows = 0
        errors: dict[str, str] = {}

        for symbol in symbol_codes:
            try:
                rows = await self._flow_service.fetch_and_store(symbol, date_from, date_to)
                succeeded += 1
                total_rows += len(rows)
            except Exception as exc:  # noqa: BLE001 - 한 종목 실패가 전체를 막지 않도록
                failed += 1
                errors[symbol] = str(exc)

        return RefreshSummary(
            requested=len(symbol_codes),
            succeeded=succeeded,
            failed=failed,
            rows=total_rows,
            errors=errors,
        )
