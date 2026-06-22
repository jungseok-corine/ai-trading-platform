from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from app.common.timezone import KST

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import SchedulerRunStatus
from app.domain.repositories.scanner import ScannerRuleVersionRepository
from app.domain.repositories.watchlist import WatchlistSymbolRepository
from app.services.assignment_service import AssignmentService
from app.services.market_context_capture_service import MarketContextCaptureService
from app.services.scanner_scan_service import ScannerScanService
from app.services.scheduler_run_service import SchedulerRunService

PIPELINE_JOB_ID = "research_pipeline"


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
    context_snapshot_id: int | None = None
    per_version: list[VersionRunResult] = field(default_factory=list)

    def to_summary_dict(self) -> dict:
        """scheduler_runs.summary(JSONB)에 저장할 dict로 직렬화한다."""
        return {
            "versions": self.versions,
            "symbols": self.symbols,
            "candidates": self.candidates,
            "assignments": self.assignments,
            "context_snapshot_id": self.context_snapshot_id,
            "per_version": [
                {
                    "scanner_rule_version_id": v.scanner_rule_version_id,
                    "scanned": v.scanned,
                    "matched": v.matched,
                    "assigned": v.assigned,
                }
                for v in self.per_version
            ],
        }


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
        self._run_service = SchedulerRunService(session)
        self._capture_service = MarketContextCaptureService(session)

    async def run_and_record(
        self,
        symbol_codes: list[str] | None = None,
        auto_assign: bool = True,
    ) -> PipelineSummary:
        """run_once를 실행하고 결과를 scheduler_runs(job_id=research_pipeline)에 기록한다.

        수동 API 실행과 스케줄 잡 모두 이 메서드를 통해 이력을 남긴다.
        """
        started_at = datetime.now(KST)
        try:
            summary = await self.run_once(symbol_codes=symbol_codes, auto_assign=auto_assign)
        except Exception as exc:  # noqa: BLE001 - 실패도 이력으로 남긴다
            await self._run_service.record_run(
                job_id=PIPELINE_JOB_ID,
                started_at=started_at,
                finished_at=datetime.now(KST),
                status=SchedulerRunStatus.FAILED,
                error_message=str(exc),
            )
            raise
        await self._run_service.record_run(
            job_id=PIPELINE_JOB_ID,
            started_at=started_at,
            finished_at=datetime.now(KST),
            status=SchedulerRunStatus.SUCCESS,
            summary=summary.to_summary_dict(),
        )
        return summary

    async def list_runs(self, limit: int = 20):
        return await self._run_service.list_by_job(PIPELINE_JOB_ID, limit)

    async def _watchlist_symbols(self) -> list[str]:
        return await WatchlistSymbolRepository(self._session).list_enabled_symbol_codes()

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

        # 이번 실행의 시장 맥락을 한 번 캡처해 모든 후보에 연결한다(versions가 있을 때만).
        context_snapshot_id: int | None = None
        if versions:
            snapshot = await self._capture_service.capture(now=now)
            context_snapshot_id = snapshot.id

        for version in versions:
            scan_result = await self._scan_service.scan_from_market_data(
                version.id, symbol_codes, now=now, context_snapshot_id=context_snapshot_id
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
            context_snapshot_id=context_snapshot_id,
            per_version=per_version,
        )
