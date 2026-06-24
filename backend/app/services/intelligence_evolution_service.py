"""Intelligence 실험 결과 → AI 분석 → 개선 제안 자동 생성 (C-2.28).

흐름:
  Experiment(COMPLETED) + IntelligenceStrategyProposal
  → build_evolution_context()
      1. ExperimentResult 지표 (trades_count, expectancy, win_rate 등)
      2. IntelligenceCandidate 컨텍스트 (why_text, matched_themes)
      3. 원본 proposal rationale + strategy_type
      4. 회고 요약 (intelligence_evolution 제안 회고 우선, 없으면 전체 회고 폴백)
  → _run_analysis() — AnalysisRunService.create_run() (LLM 호출, provider/model 설정 기반)
  → trades_count < min_trades → AI 분석만 기록, StrategyProposal 생성 금지
  → trades_count >= min_trades → AnalysisProposalService와 동등한 로직으로 pending StrategyProposal 생성
      - source="intelligence_evolution"
      - 대상 Strategy = materialize()가 생성한 paper-only Strategy
      - 항상 PENDING (자동 승인 절대 금지)

안전 원칙:
- AI 제안 자동 승인 절대 금지
- auto_trade_enabled True 절대 금지
- conclude() 내부 자동 호출 금지 (별도 단계)
- ACTIVE StrategyVersion 자동 생성 금지
- ACTIVE Strategy 수정 금지
- 주문/broker API 호출 없음
- C-2.29 이후 기능 없음
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ExperimentStatus
from app.domain.models.experiment import Experiment, ExperimentResult
from app.domain.models.intelligence_candidate import IntelligenceCandidate
from app.domain.models.intelligence_strategy_proposal import IntelligenceStrategyProposal
from app.domain.repositories.experiment import ExperimentRepository, ExperimentVariantRepository
from app.domain.repositories.intelligence_candidate import IntelligenceCandidateRepository
from app.domain.repositories.intelligence_strategy_proposal import (
    IntelligenceStrategyProposalRepository,
)
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.experiment_service import ExperimentNotFoundError
from app.services.proposal_service import ProposalService
from app.services.proposal_retrospective_service import ProposalRetrospectiveService
from app.trading.analysis.analysis_output import JSON_OUTPUT_INSTRUCTION, parse_analysis_output

EVOLUTION_STATUS_ANALYZED_NO_PROPOSAL = "analyzed_no_proposal"
EVOLUTION_STATUS_PROPOSAL_CREATED = "proposal_created"
EVOLUTION_STATUS_FAILED = "failed"


class ExperimentNotCompletedError(Exception):
    """COMPLETED 상태가 아닌 실험을 analyze하려 할 때 발생."""


class ProposalNotFoundForExperimentError(Exception):
    """experiment_id에 연결된 IntelligenceStrategyProposal이 없을 때 발생."""


class AlreadyAnalyzedError(Exception):
    """이미 evolution 분석된 실험을 force=False로 재분석하려 할 때 발생."""


@dataclass
class EvolutionResult:
    experiment_id: int
    intel_proposal_id: int | None
    analyzed: bool
    status: str
    reason: str
    trades_count: int
    min_trades_required: int
    run_id: int | None = None
    strategy_proposal_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "intel_proposal_id": self.intel_proposal_id,
            "analyzed": self.analyzed,
            "status": self.status,
            "reason": self.reason,
            "trades_count": self.trades_count,
            "min_trades_required": self.min_trades_required,
            "run_id": self.run_id,
            "strategy_proposal_id": self.strategy_proposal_id,
        }


@dataclass
class EvolutionLoopSummary:
    checked: int
    analyzed: int
    proposals_created: int
    skipped: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "checked": self.checked,
            "analyzed": self.analyzed,
            "proposals_created": self.proposals_created,
            "skipped": self.skipped,
            "errors": self.errors,
        }


class IntelligenceEvolutionService:
    """Intelligence paper 실험 결과를 AI가 분석해 개선 제안을 생성한다 (C-2.28).

    AI는 항상 제안자다. 제안은 항상 pending이며 사람 승인 전에는 반영되지 않는다.
    """

    def __init__(self, session: AsyncSession, settings=None) -> None:
        self._session = session
        if settings is None:
            from app.core.config import get_settings
            settings = get_settings()
        self._settings = settings
        self._experiment_repo = ExperimentRepository(session)
        self._variant_repo = ExperimentVariantRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._proposal_repo = IntelligenceStrategyProposalRepository(session)
        self._candidate_repo = IntelligenceCandidateRepository(session)

    # ── 공개 API ────────────────────────────────────────────────────────────────

    async def analyze_experiment(
        self,
        experiment_id: int,
        force: bool = False,
        min_trades: int = 5,
    ) -> EvolutionResult:
        """COMPLETED 실험을 AI로 분석하고, 조건 충족 시 pending StrategyProposal을 생성한다.

        Args:
            experiment_id: 분석할 Experiment ID.
            force: True이면 이미 분석된 실험도 재분석한다.
            min_trades: StrategyProposal 생성에 필요한 최소 거래 수.

        Returns:
            EvolutionResult (분석 결과 요약)

        Raises:
            ExperimentNotFoundError: 실험 없음.
            ExperimentNotCompletedError: COMPLETED 상태 아님.
            ProposalNotFoundForExperimentError: 연결된 제안 없음.
        """
        # 1. 실험 조회 + COMPLETED 확인
        experiment = await self._experiment_repo.get(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        if experiment.status != ExperimentStatus.COMPLETED:
            raise ExperimentNotCompletedError(
                f"experiment {experiment_id} is {experiment.status.value}, not completed"
            )

        # 2. 연결된 IntelligenceStrategyProposal 조회
        proposal = await self._proposal_repo.find_by_experiment_id(experiment_id)
        if proposal is None:
            raise ProposalNotFoundForExperimentError(experiment_id)

        # 3. 중복 분석 방지
        if proposal.evolution_analyzed_at is not None and not force:
            return EvolutionResult(
                experiment_id=experiment_id,
                intel_proposal_id=proposal.id,
                analyzed=False,
                status=proposal.evolution_status or EVOLUTION_STATUS_ANALYZED_NO_PROPOSAL,
                reason="already analyzed (use force=True to re-analyze)",
                trades_count=0,
                min_trades_required=min_trades,
                strategy_proposal_id=proposal.evolution_strategy_proposal_id,
            )

        # 4. ExperimentVariant → StrategyVersion → strategy_id
        variants = await self._variant_repo.list_by_experiment(experiment_id)
        if not variants:
            await self._mark_proposal(
                proposal,
                status=EVOLUTION_STATUS_FAILED,
                reason="no experiment variants found",
            )
            return EvolutionResult(
                experiment_id=experiment_id,
                intel_proposal_id=proposal.id,
                analyzed=True,
                status=EVOLUTION_STATUS_FAILED,
                reason="no experiment variants found",
                trades_count=0,
                min_trades_required=min_trades,
            )

        variant = variants[0]
        version = await self._version_repo.get(variant.strategy_version_id)
        if version is None:
            await self._mark_proposal(
                proposal,
                status=EVOLUTION_STATUS_FAILED,
                reason="strategy version not found",
            )
            return EvolutionResult(
                experiment_id=experiment_id,
                intel_proposal_id=proposal.id,
                analyzed=True,
                status=EVOLUTION_STATUS_FAILED,
                reason="strategy version not found",
                trades_count=0,
                min_trades_required=min_trades,
            )

        strategy_id = version.strategy_id

        # 5. ExperimentResult 지표 로드
        result_metrics = await self._get_result_metrics(variant.id)
        trades_count = result_metrics.get("trades_count", 0)

        # 6. IntelligenceCandidate 로드
        candidate = await self._candidate_repo.get(proposal.intelligence_candidate_id)

        # 7. 회고 요약 로드
        retro_summary = await self._build_retro_summary()

        # 8. LLM 컨텍스트 빌드
        extra_context = (
            self.build_evolution_context(experiment, proposal, candidate, result_metrics, retro_summary)
            + "\n\n"
            + JSON_OUTPUT_INSTRUCTION
        )

        # 9. LLM 분석 실행
        run = await self._run_analysis(strategy_id, version.id, extra_context)
        run_id = run.id if run else None

        # 10. 거래 수 부족 → 제안 생략
        if trades_count < min_trades:
            reason = (
                f"not enough paper trade data: {trades_count} trades < {min_trades} required"
            )
            await self._mark_proposal(
                proposal,
                status=EVOLUTION_STATUS_ANALYZED_NO_PROPOSAL,
                reason=reason,
                evolution_strategy_proposal_id=None,
            )
            return EvolutionResult(
                experiment_id=experiment_id,
                intel_proposal_id=proposal.id,
                analyzed=True,
                status=EVOLUTION_STATUS_ANALYZED_NO_PROPOSAL,
                reason=reason,
                trades_count=trades_count,
                min_trades_required=min_trades,
                run_id=run_id,
                strategy_proposal_id=None,
            )

        # 11. 거래 수 충족 → LLM 출력 파싱 → pending StrategyProposal 생성
        strategy_proposal = await self._try_create_proposal(
            run=run,
            strategy_id=strategy_id,
            version_id=version.id,
            version_params=version.parameters or {},
            run_id=run_id,
        )

        final_status = (
            EVOLUTION_STATUS_PROPOSAL_CREATED
            if strategy_proposal
            else EVOLUTION_STATUS_ANALYZED_NO_PROPOSAL
        )
        final_reason = (
            "strategy proposal created"
            if strategy_proposal
            else "AI output did not produce a valid proposal (insufficient confidence or unparseable)"
        )

        await self._mark_proposal(
            proposal,
            status=final_status,
            reason=final_reason,
            evolution_strategy_proposal_id=strategy_proposal.id if strategy_proposal else None,
        )

        return EvolutionResult(
            experiment_id=experiment_id,
            intel_proposal_id=proposal.id,
            analyzed=True,
            status=final_status,
            reason=final_reason,
            trades_count=trades_count,
            min_trades_required=min_trades,
            run_id=run_id,
            strategy_proposal_id=strategy_proposal.id if strategy_proposal else None,
        )

    async def evolution_loop(self, min_trades: int = 5) -> EvolutionLoopSummary:
        """COMPLETED experiment 중 미분석 제안을 찾아 analyze_experiment()를 실행한다.

        이미 분석된 제안(evolution_analyzed_at IS NOT NULL)은 건너뛴다.
        """
        proposals = await self._proposal_repo.list_pending_evolution()
        analyzed = 0
        proposals_created = 0
        skipped: list[int] = []
        errors: list[str] = []

        for proposal in proposals:
            if proposal.experiment_id is None:
                continue
            try:
                result = await self.analyze_experiment(
                    proposal.experiment_id, force=False, min_trades=min_trades
                )
                if result.analyzed:
                    analyzed += 1
                    if result.strategy_proposal_id is not None:
                        proposals_created += 1
                else:
                    skipped.append(proposal.experiment_id)
            except Exception as exc:
                errors.append(f"experiment {proposal.experiment_id}: {exc}")

        return EvolutionLoopSummary(
            checked=len(proposals),
            analyzed=analyzed,
            proposals_created=proposals_created,
            skipped=skipped,
            errors=errors,
        )

    def build_evolution_context(
        self,
        experiment: Experiment,
        proposal: IntelligenceStrategyProposal,
        candidate: IntelligenceCandidate | None,
        result_metrics: dict,
        retro_summary: dict,
    ) -> str:
        """LLM extra_context 문자열을 조립한다. 순수 함수(네트워크/DB 없음)."""
        trades_count = result_metrics.get("trades_count", 0)
        win_rate = result_metrics.get("win_rate")
        expectancy = result_metrics.get("expectancy")
        profit_factor = result_metrics.get("profit_factor")
        max_drawdown = result_metrics.get("max_drawdown")

        started_at = experiment.started_at
        ended_at = experiment.ended_at
        days_elapsed = 0
        if started_at and ended_at:
            days_elapsed = (ended_at - started_at).days

        why_text = ""
        matched_themes: list = []
        candidate_score = 0
        if candidate is not None:
            why_text = candidate.why_text or ""
            matched_themes = candidate.matched_themes or []
            candidate_score = candidate.score or 0

        total_retro = retro_summary.get("total", 0)
        improved = retro_summary.get("improved", 0)
        worse = retro_summary.get("worse", 0)
        inconclusive = retro_summary.get("inconclusive", 0)
        retro_source = retro_summary.get("source", "all")

        def _fmt(v, fmt=".4f"):
            return format(v, fmt) if v is not None else "N/A"

        lines = [
            "=== Intelligence Experiment Evolution Analysis (C-2.28) ===",
            "",
            "[실험 정보]",
            f"실험 ID: {experiment.id}",
            f"종목: {proposal.symbol_code} ({proposal.market.value})",
            f"전략 타입: {proposal.suggested_strategy_type}",
            f"실험 기간: {started_at} ~ {ended_at} ({days_elapsed}일)",
            "",
            "[실험 성과 지표]",
            f"거래 수: {trades_count}",
            f"승률: {_fmt(win_rate, '.1%') if win_rate is not None else 'N/A'}",
            f"기대값(expectancy): {_fmt(expectancy)}",
            f"손익비(profit_factor): {_fmt(profit_factor)}",
            f"최대 낙폭(max_drawdown): {_fmt(max_drawdown)}",
            "",
            "[후보 발굴 근거]",
            f"후보 설명: {why_text}",
            f"매칭 테마: {', '.join(str(t) for t in matched_themes) if matched_themes else 'N/A'}",
            f"후보 점수: {candidate_score}점",
            "",
            "[원본 전략 배정 근거]",
            f"제안 근거: {proposal.rationale or 'N/A'}",
            f"전략 신뢰도: {_fmt(proposal.confidence_score, '.2f') if proposal.confidence_score else 'N/A'}",
            "",
            f"[과거 Intelligence Evolution 제안 회고 (source={retro_source})]",
            f"총 제안: {total_retro}건 | 개선: {improved} | 악화: {worse} | 불충분: {inconclusive}",
            "⚠ 데이터 부족 시 과감한 파라미터 변경 금지. 성과 근거 없이 제안 생성 금지.",
            "",
            "[분석 지침]",
            f"현재 거래 수: {trades_count}건 (제안 생성 기준: {self._settings.intelligence_evolution_min_trades_for_proposal}건 이상)",
            "거래 데이터가 부족하면 'keep' verdict 권장. 원본 파라미터를 근거 없이 변경 금지.",
        ]
        return "\n".join(lines)

    # ── 내부 메서드 ─────────────────────────────────────────────────────────────

    async def _run_analysis(self, strategy_id: int, version_id: int, extra_context: str):
        """LLM 분석 실행. 테스트에서 이 메서드를 모킹한다."""
        from app.services.ai_analysis.run_service import AnalysisRunService
        s = self._settings
        run_svc = AnalysisRunService(self._session)
        return await run_svc.create_run(
            strategy_id,
            version_id,
            prompt_type=s.ai_analysis_prompt_type,
            provider_name=s.ai_analysis_provider,
            model=s.ai_analysis_model,
            mode="single",
            extra_context=extra_context,
        )

    @staticmethod
    def _get_analysis_text(run) -> str | None:
        if run is None or not getattr(run, "responses", None):
            return None
        by_role = {r.role: r.content for r in run.responses if r.content}
        return by_role.get("synthesis") or by_role.get("primary_analysis")

    async def _get_result_metrics(self, variant_id: int) -> dict:
        """ExperimentVariant의 최신 ExperimentResult 지표를 반환. 없으면 trades_count=0."""
        result = await self._session.execute(
            select(ExperimentResult)
            .where(ExperimentResult.experiment_variant_id == variant_id)
            .order_by(ExperimentResult.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return {"trades_count": 0}
        return {
            "trades_count": row.trades_count,
            "win_rate": float(row.win_rate) if row.win_rate is not None else None,
            "expectancy": float(row.expectancy) if row.expectancy is not None else None,
            "profit_factor": float(row.profit_factor) if row.profit_factor is not None else None,
            "max_drawdown": float(row.max_drawdown) if row.max_drawdown is not None else None,
        }

    async def _build_retro_summary(self) -> dict:
        """intelligence_evolution 제안 회고 요약. 데이터 없으면 전체 회고로 폴백."""
        from app.domain.models.enums import ProposalStatus
        from app.domain.models.strategy_proposal import StrategyProposal
        from app.services.proposal_retrospective_service import (
            VERDICT_IMPROVED,
            VERDICT_INCONCLUSIVE,
            VERDICT_WORSE,
        )

        result = await self._session.execute(
            select(StrategyProposal)
            .where(
                StrategyProposal.source == "intelligence_evolution",
                StrategyProposal.status == ProposalStatus.APPROVED,
            )
            .limit(50)
        )
        intel_proposals = list(result.scalars().all())

        retro_svc = ProposalRetrospectiveService(self._session)

        if not intel_proposals:
            summary = await retro_svc.summary()
            summary["source"] = "all"
            return summary

        retros = [
            await retro_svc.retrospect_strategy(p)
            for p in intel_proposals
            if p.created_version_id is not None
        ]

        if not retros:
            summary = await retro_svc.summary()
            summary["source"] = "all"
            return summary

        counts = {VERDICT_IMPROVED: 0, VERDICT_WORSE: 0, VERDICT_INCONCLUSIVE: 0}
        for r in retros:
            counts[r.verdict] = counts.get(r.verdict, 0) + 1
        return {"total": len(retros), "source": "intelligence_evolution", **counts}

    async def _try_create_proposal(
        self,
        run,
        strategy_id: int,
        version_id: int,
        version_params: dict,
        run_id: int | None,
    ):
        """LLM 출력을 파싱해 pending StrategyProposal을 생성한다.

        confidence 부족 / JSON 파싱 실패 / strategy_type 무효이면 None을 반환한다.
        자동 승인 없음 — 생성되는 제안은 항상 PENDING.
        """
        import logging
        logger = logging.getLogger(__name__)

        analysis_text = self._get_analysis_text(run)
        if not analysis_text:
            return None

        out = parse_analysis_output(analysis_text)
        if out is None:
            return None

        best = out.best_hypothesis(self._settings.ai_analysis_min_confidence)
        if best is None:
            return None

        suggested = {**version_params, **best.param_change}
        # auto_trade_enabled=True는 절대 허용하지 않는다.
        suggested.pop("auto_trade_enabled", None)
        suggested["auto_trade_enabled"] = False

        verdict = out.verdict or "improve"
        rationale = (
            best.rationale
            or "; ".join(out.mistakes)
            or "Intelligence evolution 분석 기반 개선 제안."
        )

        proposal_svc = ProposalService(self._session)
        try:
            return await proposal_svc.create_proposal(
                strategy_id=strategy_id,
                suggested_parameters=suggested,
                title=f"Intelligence Evolution: {best.hypothesis[:120]}",
                summary=f"verdict={verdict}, confidence={best.confidence}",
                rationale=rationale,
                expected_effect="; ".join(out.key_observations) or None,
                risk_notes=out.risk_notes,
                base_version_id=version_id,
                source="intelligence_evolution",
                ai_analysis_run_id=run_id,
            )
        except Exception as exc:
            logger.warning("intelligence evolution proposal rejected: %s", exc)
            return None

    async def _mark_proposal(
        self,
        proposal: IntelligenceStrategyProposal,
        status: str,
        reason: str,
        evolution_strategy_proposal_id: int | None = None,
    ) -> None:
        """제안에 evolution 추적 필드를 기록하고 커밋한다."""
        proposal.evolution_analyzed_at = datetime.now(timezone.utc)
        proposal.evolution_status = status
        proposal.evolution_reason = reason
        if evolution_strategy_proposal_id is not None:
            proposal.evolution_strategy_proposal_id = evolution_strategy_proposal_id
        await self._session.flush()
        await self._session.commit()
