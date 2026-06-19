from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.watchlist import Watchlist, WatchlistSymbol
from app.domain.repositories.scanner import ScannerRuleVersionRepository
from app.services.assignment_service import AssignmentService
from app.services.scanner_scan_service import ScannerScanService


@dataclass
class VersionRunResult:
    scanner_rule_version_id: int
    scanned: int
    matched: int
    assigned: int


@dataclass
class PipelineSummary:
    """파이프라인 1회 실행 요약."""

    versions: int
    symbols: int
    candidates: int
    assignments: int
    per_version: list[VersionRunResult] = field(default_factory=list)


class ResearchPipelineService:
    """연구 루프를 한 번에 자동으로 돌린다 (C-2.35).

    active/testing 스캐너 룰 버전을 watchlist 종목에 대해 스캔(facts 자동계산)해 후보를
    기록하고, 각 후보에 매칭되는 배정 규칙으로 전략을 자동 배정한다.
    "스캔 → 후보 → 전략배정"을 수동 API 호출 없이 잇는 핵심 고리다.
    주문은 발생하지 않는다(배정은 로그만 남기며 strategy_version을 만들지 않음).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._version_repo = ScannerRuleVersionRepository(session)
        self._scan_service = ScannerScanService(session)
        self._assignment_service = AssignmentService(session)

    async def _watchlist_symbols(self) -> list[str]:
        result = await self._session.execute(
            select(WatchlistSymbol.symbol_code)
            .join(Watchlist, Watchlist.id == WatchlistSymbol.watchlist_id)
            .where(Watchlist.enabled.is_(True), WatchlistSymbol.enabled.is_(True))
            .distinct()
        )
        return [row[0] for row in result.all()]

    async def run_once(
        self,
        symbol_codes: list[str] | None = None,
        auto_assign: bool = True,
        now: datetime | None = None,
    ) -> PipelineSummary:
        """active/testing 스캐너 버전 전체를 1회 실행한다.

        symbol_codes 미지정 시 enabled watchlist 종목을 대상으로 한다.
        """
        if symbol_codes is None:
            symbol_codes = await self._watchlist_symbols()

        versions = await self._version_repo.list_active()
        per_version: list[VersionRunResult] = []
        total_candidates = 0
        total_assignments = 0

        for version in versions:
            scan_result = await self._scan_service.scan_from_market_data(
                version.id, symbol_codes, now=now
            )
            assigned = 0
            if auto_assign:
                for candidate in scan_result.candidates:
                    log = await self._assignment_service.assign(candidate.id)
                    if log is not None:
                        assigned += 1

            total_candidates += scan_result.matched
            total_assignments += assigned
            per_version.append(
                VersionRunResult(
                    scanner_rule_version_id=version.id,
                    scanned=scan_result.scanned,
                    matched=scan_result.matched,
                    assigned=assigned,
                )
            )

        return PipelineSummary(
            versions=len(versions),
            symbols=len(symbol_codes),
            candidates=total_candidates,
            assignments=total_assignments,
            per_version=per_version,
        )
