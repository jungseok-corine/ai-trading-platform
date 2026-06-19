from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import (
    ProposalStatus,
    ScannerRuleStatus,
    StrategyVersionStatus,
)
from app.domain.models.scanner import ScannerRuleVersion
from app.domain.models.scanner_proposal import ScannerRuleProposal
from app.domain.models.strategy import StrategyVersion
from app.domain.models.strategy_proposal import StrategyProposal
from app.domain.repositories.scheduler_run import SchedulerRunRepository
from app.services.proposal_retrospective_service import ProposalRetrospectiveService

# 자율 연구 루프를 구성하는 잡들. 운영자가 한눈에 보도록 모은다.
RESEARCH_JOB_IDS = ("research_pipeline", "scanner_review", "strategy_review", "daily_report")


@dataclass
class JobStatus:
    job_id: str
    last_run_at: datetime | None
    status: str | None
    duration_ms: int | None
    error_message: str | None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
        }


@dataclass
class ResearchStatus:
    jobs: list[JobStatus]
    pending: dict
    active: dict
    retrospective: dict

    def to_dict(self) -> dict:
        return {
            "jobs": [j.to_dict() for j in self.jobs],
            "pending": self.pending,
            "active": self.active,
            "retrospective": self.retrospective,
        }


class ResearchStatusService:
    """자율 연구 루프의 '관제탑' 상태를 한 번에 모은다 (C-2.43).

    각 자율 잡의 최근 실행 상태 + 검토 대기(pending) 제안 수 + 활성 버전 수를 집계한다.
    read-only 집계이며 주문/외부 호출이 없다. 운영자가 "지금 무엇이 돌고 있고, 무엇을
    검토해야 하는가"를 단일 화면에서 보도록 한다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._run_repo = SchedulerRunRepository(session)
        self._retro_service = ProposalRetrospectiveService(session)

    async def status(self) -> ResearchStatus:
        jobs: list[JobStatus] = []
        for job_id in RESEARCH_JOB_IDS:
            run = await self._run_repo.latest_by_job(job_id)
            jobs.append(
                JobStatus(
                    job_id=job_id,
                    last_run_at=run.started_at if run else None,
                    status=run.status.value if run else None,
                    duration_ms=run.duration_ms if run else None,
                    error_message=run.error_message if run else None,
                )
            )

        strategy_pending = await self._count_status(StrategyProposal, ProposalStatus.PENDING)
        scanner_pending = await self._count_status(ScannerRuleProposal, ProposalStatus.PENDING)
        active_scanner = await self._count_in(
            ScannerRuleVersion,
            [ScannerRuleStatus.ACTIVE, ScannerRuleStatus.TESTING],
        )
        active_strategy = await self._count_in(
            StrategyVersion,
            [StrategyVersionStatus.ACTIVE, StrategyVersionStatus.TESTING],
        )

        retrospective = await self._retro_service.summary()

        return ResearchStatus(
            jobs=jobs,
            pending={
                "strategy": strategy_pending,
                "scanner": scanner_pending,
                "total": strategy_pending + scanner_pending,
            },
            active={
                "scanner_versions": active_scanner,
                "strategy_versions": active_strategy,
            },
            retrospective=retrospective,
        )

    async def _count_status(self, model, status: ProposalStatus) -> int:
        result = await self._session.execute(
            select(func.count(model.id)).where(model.status == status)
        )
        return result.scalar() or 0

    async def _count_in(self, model, statuses: list) -> int:
        result = await self._session.execute(
            select(func.count(model.id)).where(model.status.in_(statuses))
        )
        return result.scalar() or 0
