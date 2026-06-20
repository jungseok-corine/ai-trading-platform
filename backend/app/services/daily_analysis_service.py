from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import AnalysisRunMode, SchedulerRunStatus
from app.domain.repositories.signal_log import SignalLogRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.ai_analysis.run_service import AnalysisRunService
from app.services.analysis_bundle_service import AnalysisBundleService
from app.services.analysis_proposal_service import AnalysisProposalService
from app.services.scheduler_run_service import SchedulerRunService
from app.trading.analysis.activity import assess_activity
from app.trading.analysis.analysis_output import JSON_OUTPUT_INSTRUCTION
from app.trading.analysis.bundle_prompt import format_bundle_for_prompt

KST = ZoneInfo("Asia/Seoul")
DAILY_ANALYSIS_JOB_ID = "daily_analysis"


@dataclass
class VersionAnalysisResult:
    strategy_version_id: int
    band: str
    analyzed: bool
    run_id: int | None = None
    run_status: str | None = None
    proposal_id: int | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "strategy_version_id": self.strategy_version_id,
            "band": self.band,
            "analyzed": self.analyzed,
            "run_id": self.run_id,
            "run_status": self.run_status,
            "proposal_id": self.proposal_id,
            "reason": self.reason,
        }


@dataclass
class DailyAnalysisSummary:
    trading_day: str
    versions: int
    analyzed: int
    skipped: int
    mode: str
    provider: str
    proposals: int = 0
    per_version: list[VersionAnalysisResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "trading_day": self.trading_day,
            "versions": self.versions,
            "analyzed": self.analyzed,
            "skipped": self.skipped,
            "mode": self.mode,
            "provider": self.provider,
            "proposals": self.proposals,
            "per_version": [v.to_dict() for v in self.per_version],
        }


class DailyAnalysisService:
    """장마감 후 활성 전략 버전을 일괄 분석한다 (C-2.54).

    활동량 게이트(assess_activity)로 분석 여부를 정한다 — 무신호 + 시장 비활발이면 생략하고,
    '신호 적음 + 시장 활발'(조건 과빡 의심) 같은 케이스는 오히려 분석한다. 분석은
    AnalysisRunService(single/dual)로 수행하며, provider/model/mode는 설정에서 읽는다.
    기본 provider는 fake라 실수로 유료 호출이 일어나지 않는다(사람이 명시적으로 켠다).
    """

    def __init__(self, session: AsyncSession, settings=None) -> None:
        self._session = session
        if settings is None:
            from app.core.config import get_settings

            settings = get_settings()
        self._settings = settings
        self._version_repo = StrategyVersionRepository(session)
        self._signal_repo = SignalLogRepository(session)
        self._bundle_svc = AnalysisBundleService(session)
        self._run_svc = AnalysisRunService(session)
        self._proposal_svc = AnalysisProposalService(session)
        self._scheduler_run_svc = SchedulerRunService(session)

    async def run_once(self, trading_day: date | None = None) -> DailyAnalysisSummary:
        s = self._settings
        if trading_day is None:
            trading_day = datetime.now(KST).date()
        start = datetime.combine(trading_day, time.min, tzinfo=KST)
        end = start + timedelta(days=1)

        versions = await self._version_repo.list_active()
        results: list[VersionAnalysisResult] = []
        analyzed = 0
        skipped = 0
        proposals = 0

        for version in versions:
            bundle = await self._bundle_svc.build_full(version.id, trading_day)
            tape = (bundle or {}).get("trade_tape") or {}
            day_summary = tape.get("day_summary") or {}
            range_pct = day_summary.get("range_pct")
            notable = len(tape.get("notable_events", []))

            day_signals = await self._signal_repo.list_filtered(
                strategy_version_id=version.id, date_from=start, date_to=end, limit=1000
            )
            assessment = assess_activity(
                len(day_signals), range_pct, notable,
                few_threshold=s.ai_analysis_few_threshold,
                many_threshold=s.ai_analysis_many_threshold,
                active_range_pct=s.ai_analysis_active_range_pct,
                active_notable=s.ai_analysis_active_notable,
            )

            if not assessment.should_analyze:
                skipped += 1
                results.append(VersionAnalysisResult(
                    strategy_version_id=version.id, band=assessment.band,
                    analyzed=False, reason=assessment.reason,
                ))
                continue

            extra_context = (
                format_bundle_for_prompt(bundle or {}, assessment.to_dict())
                + "\n\n" + JSON_OUTPUT_INSTRUCTION
            )
            run = await self._run_analysis(version.strategy_id, version.id, extra_context)
            analyzed += 1

            # 분석 출력(JSON)을 검증해 pending 제안으로 연결한다(C-2.56).
            proposal_id = await self._maybe_propose(version.strategy_id, version.id, run)
            if proposal_id is not None:
                proposals += 1
            results.append(VersionAnalysisResult(
                strategy_version_id=version.id, band=assessment.band, analyzed=True,
                run_id=run.id if run else None,
                run_status=run.status.value if run else None,
                proposal_id=proposal_id,
                reason=assessment.reason,
            ))

        return DailyAnalysisSummary(
            trading_day=trading_day.isoformat(), versions=len(versions),
            analyzed=analyzed, skipped=skipped, mode=s.ai_analysis_mode,
            provider=s.ai_analysis_provider, proposals=proposals, per_version=results,
        )

    @staticmethod
    def _analysis_text(run) -> str | None:
        """run 응답에서 분석 본문을 고른다(synthesis > primary_analysis)."""
        if run is None or not getattr(run, "responses", None):
            return None
        by_role = {r.role: r.content for r in run.responses if r.content}
        return by_role.get("synthesis") or by_role.get("primary_analysis")

    async def _maybe_propose(self, strategy_id: int, version_id: int, run) -> int | None:
        text = self._analysis_text(run)
        if not text:
            return None
        proposal = await self._proposal_svc.create_from_text(
            strategy_id, version_id, text, ai_analysis_run_id=run.id,
            min_confidence=self._settings.ai_analysis_min_confidence,
        )
        return proposal.id if proposal else None

    async def _run_analysis(self, strategy_id: int, version_id: int, extra_context: str):
        s = self._settings
        mode = s.ai_analysis_mode
        if mode == AnalysisRunMode.DUAL.value:
            return await self._run_svc.create_run(
                strategy_id, version_id, prompt_type=s.ai_analysis_prompt_type,
                provider_name=s.ai_analysis_provider, model=s.ai_analysis_model,
                mode="dual",
                secondary_provider_name=s.ai_analysis_secondary_provider,
                secondary_model=s.ai_analysis_secondary_model,
                extra_context=extra_context,
            )
        return await self._run_svc.create_run(
            strategy_id, version_id, prompt_type=s.ai_analysis_prompt_type,
            provider_name=s.ai_analysis_provider, model=s.ai_analysis_model, mode="single",
            extra_context=extra_context,
        )

    async def run_and_record(self, trading_day: date | None = None) -> DailyAnalysisSummary:
        started_at = datetime.now(KST)
        try:
            summary = await self.run_once(trading_day=trading_day)
        except Exception as exc:  # noqa: BLE001 - 실패도 이력으로 남긴다
            await self._scheduler_run_svc.record_run(
                job_id=DAILY_ANALYSIS_JOB_ID, started_at=started_at,
                finished_at=datetime.now(KST), status=SchedulerRunStatus.FAILED,
                error_message=str(exc),
            )
            raise
        await self._scheduler_run_svc.record_run(
            job_id=DAILY_ANALYSIS_JOB_ID, started_at=started_at,
            finished_at=datetime.now(KST), status=SchedulerRunStatus.SUCCESS,
            summary=summary.to_dict(),
        )
        return summary

    async def list_runs(self, limit: int = 20):
        return await self._scheduler_run_svc.list_by_job(DAILY_ANALYSIS_JOB_ID, limit)
