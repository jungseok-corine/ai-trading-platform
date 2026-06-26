"""Paper Signal Challenger Session Preparation + Activation (M2.5 Phase 2 + Phase 3).

M2.2가 만든 **DRAFT challenger StrategyVersion**(proposal.created_version_id)에 대해, 사람이 명시
확인하면 **비실행(prepared) PaperSignalSession**을 만들고(Phase 2), 이후 사람이 다시 명시 확인하면
**prepared→active 전환**(Phase 3)만 한다.

핵심 안전 불변식 (D-20, D-21):
- 준비 세션은 `status="prepared"` — `PaperSignalSessionRepository.list_active()`(status=='active')
  비대상 → 런너가 보지 못한다. 활성화는 status를 active로만 바꿔 **런너 대상 자격**만 부여한다.
- **활성화는 신호를 즉시 만들지 않는다.** SignalLog는 전용 `paper_signal_session_runner` 잡이 켜져 있고
  실행될 때만 `run_due_sessions`가 만든다. 활성화는 잡을 켜지 않고, run_due_sessions를 호출하지 않는다.
- `candidate_strategy_proposal_id=NULL`, `source_type="signal_challenger"`,
  `source_strategy_proposal_id=proposal.id`, `baseline_session_id`=분석 run의 대상 세션.
- StrategyVersion/Experiment/SignalLog/Trade/Order/AssignmentLog를 만들지 않는다. approve 미호출.
  TradeService/OrderService/StrategyRunnerService/broker/KIS 미접촉. auto_trade를 켜지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
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


# --- Phase 3 (activation) 에러 ---
class ActivationSessionNotFoundError(Exception):
    """session_id가 존재하지 않을 때 (404)."""


class NotChallengerSessionError(Exception):
    """세션 source_type이 signal_challenger가 아닐 때 (422)."""


class SessionNotPreparedError(Exception):
    """세션 status가 prepared가 아닐 때 (422)."""


class InconsistentSessionError(Exception):
    """challenger 세션 링크가 불완전할 때(candidate FK·source 제안·baseline·version) (422)."""


class LinkedProposalInvalidError(Exception):
    """연결된 StrategyProposal이 없거나 source/status/created_version 불일치 (422)."""


class DuplicateActiveChallengerError(Exception):
    """같은 source 제안에 (현재 세션 외) 이미 active challenger 세션이 있을 때 (409)."""


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

    async def activate_prepared_session(
        self, session_id: int, confirmed: bool, confirmed_by: str | None
    ) -> ChallengerSessionActivation:
        """prepared challenger 세션을 active로 전환한다(런너 대상 자격만 부여).

        **신호를 즉시 만들지 않는다.** 잡을 켜지 않고 run_due_sessions를 호출하지 않는다.
        StrategyVersion/Experiment/Trade/Order/SignalLog 변경·생성 없음. 세션 status만 바꾼다.
        """
        if not confirmed:
            raise ConfirmationRequiredError("confirmed must be true")
        if not confirmed_by:
            raise ConfirmationRequiredError("confirmed_by is required")

        sess = await self._session_repo.get(session_id)
        if sess is None:
            raise ActivationSessionNotFoundError(session_id)
        if sess.source_type != "signal_challenger":
            raise NotChallengerSessionError(
                f"session {session_id} source_type is {sess.source_type!r}, not signal_challenger"
            )
        if sess.status != "prepared":
            raise SessionNotPreparedError(
                f"session {session_id} status is {sess.status!r}, not prepared"
            )
        # 링크 일관성: challenger 세션은 candidate FK가 NULL이고 source/baseline/version이 있어야 한다.
        if sess.candidate_strategy_proposal_id is not None:
            raise InconsistentSessionError(
                f"session {session_id} has candidate_strategy_proposal_id set — not a pure challenger"
            )
        if sess.source_strategy_proposal_id is None:
            raise InconsistentSessionError(f"session {session_id} has no source_strategy_proposal_id")
        if sess.baseline_session_id is None:
            raise InconsistentSessionError(f"session {session_id} has no baseline_session_id")
        if sess.strategy_version_id is None:
            raise InconsistentSessionError(f"session {session_id} has no strategy_version_id")

        # 연결된 challenger 버전 검증(여전히 DRAFT + auto_trade off).
        version = await self._version_repo.get(sess.strategy_version_id)
        if version is None:
            raise InconsistentSessionError(
                f"challenger strategy_version {sess.strategy_version_id} not found"
            )
        if version.status != StrategyVersionStatus.DRAFT:
            raise ChallengerVersionNotDraftError(
                f"challenger version {version.id} is {version.status.value}, not draft"
            )
        if (version.parameters or {}).get("auto_trade_enabled"):
            raise ChallengerAutoTradeError(
                f"challenger version {version.id} has auto_trade_enabled=true — refusing to activate"
            )

        # 연결된 제안 검증(여전히 paper_signal_analysis · PENDING · created_version 일치).
        proposal = await self._proposal_repo.get(sess.source_strategy_proposal_id)
        if proposal is None:
            raise LinkedProposalInvalidError(
                f"source strategy_proposal {sess.source_strategy_proposal_id} not found"
            )
        if proposal.source != SIGNAL_TRACK_SOURCE:
            raise LinkedProposalInvalidError(
                f"source proposal {proposal.id} source is {proposal.source!r}, not {SIGNAL_TRACK_SOURCE!r}"
            )
        if proposal.status != ProposalStatus.PENDING:
            raise LinkedProposalInvalidError(
                f"source proposal {proposal.id} status is {proposal.status.value}, not pending"
            )
        if proposal.created_version_id != sess.strategy_version_id:
            raise LinkedProposalInvalidError(
                f"source proposal {proposal.id} created_version_id {proposal.created_version_id} "
                f"!= session strategy_version_id {sess.strategy_version_id}"
            )

        # 중복 active challenger(현재 세션 제외) 거부.
        other_active = await self._session_repo.find_active_challenger_for_strategy_proposal(
            sess.source_strategy_proposal_id, exclude_session_id=sess.id
        )
        if other_active is not None:
            raise DuplicateActiveChallengerError(
                f"proposal {sess.source_strategy_proposal_id} already has an active challenger "
                f"session ({other_active.id})"
            )

        # --- 세션 status만 prepared→active (런너 대상 자격 부여) ---
        await self._session_repo.update(
            sess,
            status="active",
            started_by=confirmed_by,
            started_at=datetime.now(timezone.utc),
        )
        await self._session.commit()

        runner_enabled = bool(get_settings().paper_signal_session_runner_enabled)
        warnings = [
            "Activation does not create signals immediately.",
            "Signal records will be generated only when the paper signal runner is enabled and runs.",
            "No orders or trades are created by this activation.",
        ]
        if runner_enabled:
            warnings.append(
                "paper_signal_session_runner is currently ENABLED; signals may be recorded on the "
                "next scheduled run (still no orders/trades)."
            )

        return ChallengerSessionActivation(
            session_id=sess.id,
            status=sess.status,
            source_type=sess.source_type,
            source_strategy_proposal_id=sess.source_strategy_proposal_id,
            baseline_session_id=sess.baseline_session_id,
            strategy_version_id=sess.strategy_version_id,
            runner_eligible=True,
            runner_currently_enabled=runner_enabled,
            warnings=warnings,
        )


@dataclass
class ChallengerSessionActivation:
    session_id: int
    status: str  # 항상 "active"
    source_type: str  # 항상 "signal_challenger"
    source_strategy_proposal_id: int
    baseline_session_id: int
    strategy_version_id: int
    runner_eligible: bool  # 항상 True (active = 런너 대상 자격)
    runner_currently_enabled: bool  # 현재 잡 config 플래그
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "source_type": self.source_type,
            "source_strategy_proposal_id": self.source_strategy_proposal_id,
            "baseline_session_id": self.baseline_session_id,
            "strategy_version_id": self.strategy_version_id,
            "runner_eligible": self.runner_eligible,
            "runner_currently_enabled": self.runner_currently_enabled,
            "warnings": self.warnings,
        }


__all__ = [
    "PaperSignalChallengerSessionService",
    "ChallengerSessionPreparation",
    "ChallengerSessionActivation",
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
    "ActivationSessionNotFoundError",
    "NotChallengerSessionError",
    "SessionNotPreparedError",
    "InconsistentSessionError",
    "LinkedProposalInvalidError",
    "DuplicateActiveChallengerError",
]
