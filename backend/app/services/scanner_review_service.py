from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import SchedulerRunStatus
from app.domain.repositories.scanner import ScannerRuleVersionRepository
from app.domain.repositories.scanner_proposal import ScannerRuleProposalRepository
from app.services.scanner_proposal_generator import ScannerProposalGenerator
from app.services.scheduler_run_service import SchedulerRunService

KST = ZoneInfo("Asia/Seoul")
SCANNER_REVIEW_JOB_ID = "scanner_review"


@dataclass
class ReviewSummary:
    """스캐너 룰 자동 점검 1회 실행 요약."""

    versions_reviewed: int
    proposals_created: int
    skipped_existing: int
    created_proposal_ids: list[int] = field(default_factory=list)

    def to_summary_dict(self) -> dict:
        return {
            "versions_reviewed": self.versions_reviewed,
            "proposals_created": self.proposals_created,
            "skipped_existing": self.skipped_existing,
            "created_proposal_ids": self.created_proposal_ids,
        }


class ScannerReviewService:
    """active/testing 스캐너 룰 버전을 주기적으로 점검해 개선 제안을 자동 생성한다 (C-2.40).

    각 버전의 후보 성과(C-2.38)를 분석해 승률이 낮으면 '조건 강화' 제안(C-2.39)을 만든다.
    제안은 pending으로만 남으며 사람 승인 전에는 룰에 반영되지 않는다. 같은 버전에 이미
    pending 제안이 있으면 건너뛰어 중복 제안을 막는다. 주문/외부 API 호출이 없는 메타 작업이다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._version_repo = ScannerRuleVersionRepository(session)
        self._proposal_repo = ScannerRuleProposalRepository(session)
        self._generator = ScannerProposalGenerator(session)
        self._run_service = SchedulerRunService(session)

    async def review(self, horizon_minutes: int = 30) -> ReviewSummary:
        versions = await self._version_repo.list_active()
        pending_ids = await self._proposal_repo.pending_base_version_ids()

        created_ids: list[int] = []
        skipped = 0
        for version in versions:
            if version.id in pending_ids:
                skipped += 1
                continue
            proposal = await self._generator.generate_for_version(
                version.id, horizon_minutes=horizon_minutes
            )
            if proposal is not None:
                created_ids.append(proposal.id)

        return ReviewSummary(
            versions_reviewed=len(versions),
            proposals_created=len(created_ids),
            skipped_existing=skipped,
            created_proposal_ids=created_ids,
        )

    async def review_and_record(self, horizon_minutes: int = 30) -> ReviewSummary:
        """review를 실행하고 결과를 scheduler_runs(job_id=scanner_review)에 기록한다."""
        started_at = datetime.now(KST)
        try:
            summary = await self.review(horizon_minutes=horizon_minutes)
        except Exception as exc:  # noqa: BLE001 - 실패도 이력으로 남긴다
            await self._run_service.record_run(
                job_id=SCANNER_REVIEW_JOB_ID,
                started_at=started_at,
                finished_at=datetime.now(KST),
                status=SchedulerRunStatus.FAILED,
                error_message=str(exc),
            )
            raise
        await self._run_service.record_run(
            job_id=SCANNER_REVIEW_JOB_ID,
            started_at=started_at,
            finished_at=datetime.now(KST),
            status=SchedulerRunStatus.SUCCESS,
            summary=summary.to_summary_dict(),
        )
        return summary

    async def list_runs(self, limit: int = 20):
        return await self._run_service.list_by_job(SCANNER_REVIEW_JOB_ID, limit)
