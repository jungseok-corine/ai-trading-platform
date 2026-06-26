"""Paper Signal Challenger Session Preparation (M2.5 Phase 2).

M2.2가 만든 **DRAFT challenger StrategyVersion**(proposal.created_version_id)에 대해, 사람이 명시
확인하면 **비실행(prepared) PaperSignalSession**을 만든다. **세션 시작이 아니다.**

핵심 안전 불변식 (D-20):
- 생성 세션은 `status="prepared"` — `PaperSignalSessionRepository.list_active()`(status=='active')
  비대상 → 런너가 절대 보지 못한다(신호 생성 없음). 시작(prepared→active)은 **별도 사람-게이트 단계**(미구현).
- `candidate_strategy_proposal_id=NULL`, `source_type="signal_challenger"`,
  `source_strategy_proposal_id=proposal.id`, `baseline_session_id`=분석 run의 대상 세션.
- StrategyVersion/Experiment/SignalLog/Trade/Order/AssignmentLog를 만들지 않는다. approve 미호출.
  TradeService/OrderService/StrategyRunnerService/broker/KIS 미접촉. auto_trade를 켜지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import AnalysisTargetType, ProposalStatus, StrategyVersionStatus
from app.domain.repositories.ai_analysis import AiAnalysisRunRepository
from app.domain.repositories.paper_signal_session import PaperSignalSessionRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.domain.repositories.strategy_proposal import StrategyProposalRepository
from app.services.paper_signal_challenger_service import SIGNAL_TRACK_SOURCE


class ChallengerSessionProposalNotFoundError(Exception):
    """proposal_id가 존재하지 않을 때 (404)."""


class ConfirmationRequiredError(Exception):
    """confirmed/confirmed_by 누락 (422)."""


class NotSignalProposalError(Exception):
    """제안 source가 paper_signal_analysis가 아닐 때 (422)."""


class ProposalNotPendingError(Exception):
    """제안이 PENDING이 아닐 때 (422)."""


class MissingChallengerVersionError(Exception):
    """created_version_id 누락 / 버전 없음 / strategy 불일치 (422). M2.2 prepare가 선행돼야 한다."""


class ChallengerVersionNotDraftError(Exception):
    """challenger 버전이 DRAFT가 아닐 때 (422)."""


class ChallengerAutoTradeError(Exception):
    """challenger 버전이 auto_trade_enabled=true일 때 (422) — 거부."""


class MissingAnalysisRunError(Exception):
    """ai_analysis_run_id 누락 / run 없음 / target_type 불일치 (422)."""


class BaselineSessionMissingError(Exception):
    """분석 run이 가리키는 baseline PaperSignalSession이 없을 때 (422)."""


class DuplicateChallengerSessionError(Exception):
    """같은 source 제안에 이미 prepared/active challenger 세션이 있을 때 (409)."""


@dataclass
class ChallengerSessionPreparation:
    session_id: int
    status: str  # 항상 "prepared"
    source_type: str  # 항상 "signal_challenger"
    source_strategy_proposal_id: int
    baseline_session_id: int
    challenger_version_id: int
    symbol_code: str
    runner_eligible: bool  # 항상 False
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "source_type": self.source_type,
            "source_strategy_proposal_id": self.source_strategy_proposal_id,
            "baseline_session_id": self.baseline_session_id,
            "challenger_version_id": self.challenger_version_id,
            "symbol_code": self.symbol_code,
            "runner_eligible": self.runner_eligible,
            "warnings": self.warnings,
        }


class PaperSignalChallengerSessionService:
    """DRAFT challenger 버전에 대한 비실행(prepared) PaperSignalSession을 준비한다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._proposal_repo = StrategyProposalRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._run_repo = AiAnalysisRunRepository(session)
        self._session_repo = PaperSignalSessionRepository(session)

    async def prepare_from_strategy_proposal(
        self, proposal_id: int, confirmed: bool, confirmed_by: str | None
    ) -> ChallengerSessionPreparation:
        # --- 확인 게이트 ---
        if not confirmed:
            raise ConfirmationRequiredError("confirmed must be true")
        if not confirmed_by:
            raise ConfirmationRequiredError("confirmed_by is required")

        # --- 제안 자격 ---
        proposal = await self._proposal_repo.get(proposal_id)
        if proposal is None:
            raise ChallengerSessionProposalNotFoundError(proposal_id)
        if proposal.source != SIGNAL_TRACK_SOURCE:
            raise NotSignalProposalError(
                f"proposal {proposal_id} source is {proposal.source!r}, not {SIGNAL_TRACK_SOURCE!r}"
            )
        if proposal.status != ProposalStatus.PENDING:
            raise ProposalNotPendingError(
                f"proposal {proposal_id} status is {proposal.status.value}, not pending"
            )

        # --- 분석 run + baseline 세션 ---
        if proposal.ai_analysis_run_id is None:
            raise MissingAnalysisRunError(f"proposal {proposal_id} has no ai_analysis_run_id")
        run = await self._run_repo.get(proposal.ai_analysis_run_id)
        if run is None:
            raise MissingAnalysisRunError(f"ai_analysis_run {proposal.ai_analysis_run_id} not found")
        if run.target_type != AnalysisTargetType.PAPER_SIGNAL_SESSION:
            raise MissingAnalysisRunError(
                f"run {run.id} target_type is {run.target_type.value}, not paper_signal_session"
            )
        baseline = await self._session_repo.get(run.target_id)
        if baseline is None:
            raise BaselineSessionMissingError(
                f"baseline paper_signal_session {run.target_id} (run target) not found"
            )

        # --- challenger 버전 (M2.2가 생성한 DRAFT) ---
        if proposal.created_version_id is None:
            raise MissingChallengerVersionError(
                f"proposal {proposal_id} has no created_version_id — prepare DRAFT challenger first"
            )
        version = await self._version_repo.get(proposal.created_version_id)
        if version is None:
            raise MissingChallengerVersionError(
                f"challenger strategy_version {proposal.created_version_id} not found"
            )
        if version.strategy_id != proposal.strategy_id:
            raise MissingChallengerVersionError(
                f"challenger version {version.id} belongs to strategy {version.strategy_id}, "
                f"not proposal strategy {proposal.strategy_id}"
            )
        if version.status != StrategyVersionStatus.DRAFT:
            raise ChallengerVersionNotDraftError(
                f"challenger version {version.id} is {version.status.value}, not draft"
            )
        if (version.parameters or {}).get("auto_trade_enabled"):
            raise ChallengerAutoTradeError(
                f"challenger version {version.id} has auto_trade_enabled=true — refusing to prepare"
            )

        # --- 중복 prepared/active challenger 세션 거부 ---
        existing = await self._session_repo.find_open_challenger_for_strategy_proposal(proposal.id)
        if existing is not None:
            raise DuplicateChallengerSessionError(
                f"proposal {proposal_id} already has an open challenger session ({existing.id}, "
                f"status={existing.status})"
            )

        # --- symbol_code: baseline 세션에서 가져온다(안전 출처) ---
        symbol_code = baseline.symbol_code
        warnings: list[str] = []
        version_symbol = (version.parameters or {}).get("symbol_code")
        if version_symbol and version_symbol != symbol_code:
            warnings.append(
                f"challenger version symbol_code {version_symbol!r} differs from baseline "
                f"session symbol_code {symbol_code!r}; using baseline symbol."
            )

        # --- 비실행(prepared) 세션 1개 생성 — 시작 아님, SignalLog 없음 ---
        sess = await self._session_repo.create(
            candidate_strategy_proposal_id=None,
            source_type="signal_challenger",
            source_strategy_proposal_id=proposal.id,
            baseline_session_id=baseline.id,
            strategy_version_id=version.id,
            symbol_code=symbol_code,
            status="prepared",
            started_by=confirmed_by,
        )
        await self._session.commit()

        return ChallengerSessionPreparation(
            session_id=sess.id,
            status=sess.status,
            source_type=sess.source_type,
            source_strategy_proposal_id=proposal.id,
            baseline_session_id=baseline.id,
            challenger_version_id=version.id,
            symbol_code=symbol_code,
            runner_eligible=False,
            warnings=warnings,
        )


__all__ = [
    "PaperSignalChallengerSessionService",
    "ChallengerSessionPreparation",
    "ChallengerSessionProposalNotFoundError",
    "ConfirmationRequiredError",
    "NotSignalProposalError",
    "ProposalNotPendingError",
    "MissingChallengerVersionError",
    "ChallengerVersionNotDraftError",
    "ChallengerAutoTradeError",
    "MissingAnalysisRunError",
    "BaselineSessionMissingError",
    "DuplicateChallengerSessionError",
]
