"""Paper Signal DRAFT Challenger Preparation (M2.2).

paper_signal_analysis 트랙의 PENDING StrategyProposal에서 **DRAFT 전용** challenger
StrategyVersion을 준비한다. **이것은 제안 승인도, 기존 approve/머티리얼라이즈 경로도 아니다.**

핵심 안전 불변식 (D-17):
- 공유 `ProposalService.approve`는 **TESTING** 버전을 만들고, runner의 `list_active()`가
  ACTIVE/**TESTING**을 실행 대상으로 잡는다. 그래서 이 서비스는 **approve를 호출하지 않고**,
  `StrategyService.create_version(status=DRAFT)`로 **DRAFT** 버전만 만든다. DRAFT는 `list_active()`
  비대상 → runner가 절대 보지 못한다(신호 생성 없음).
- `auto_trade_enabled`는 제안 내용과 무관하게 **항상 False로 강제**한다.
- 제안 상태는 **PENDING 그대로** 유지한다(승인 아님). 추적은 `created_version_id` 링크로만 한다.
- 세션 시작/중지·실험 생성·SignalLog/Trade/Order·스케줄러 잡·브로커/KIS 없음.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import (
    AnalysisTargetType,
    ProposalStatus,
    StrategyVersionStatus,
)
from app.domain.repositories.ai_analysis import AiAnalysisRunRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.domain.repositories.strategy_proposal import StrategyProposalRepository
from app.services.proposal_service import compute_diff
from app.services.strategy_service import StrategyService
from app.trading.strategy.registry import registered_types

# paper-signal 트랙 제안의 source 값(M1과 동일). 이 값만 challenger 준비 대상.
SIGNAL_TRACK_SOURCE = "paper_signal_analysis"


class ChallengerProposalNotFoundError(Exception):
    """proposal_id가 존재하지 않을 때 (404)."""


class ConfirmationRequiredError(Exception):
    """confirmed/confirmed_by 누락 (422)."""


class NotSignalProposalError(Exception):
    """제안 source가 paper_signal_analysis가 아닐 때 (422)."""


class MissingAnalysisRunError(Exception):
    """ai_analysis_run_id 누락 / run 없음 / target_type 불일치 (422)."""


class MissingBaseVersionError(Exception):
    """base_version_id 누락 / 버전 없음 / strategy 불일치 (422)."""


class InvalidChallengerParamsError(Exception):
    """병합된 파라미터가 검증을 통과하지 못할 때 (422)."""


class ProposalNotPendingError(Exception):
    """제안이 PENDING이 아닐 때 (422)."""


class ChallengerAlreadyPreparedError(Exception):
    """이미 created_version_id가 채워져 있을 때 (409, 중복 준비)."""


@dataclass
class ChallengerPreparation:
    proposal_id: int
    source_analysis_run_id: int | None
    source_session_id: int | None
    base_version_id: int
    challenger_version_id: int
    challenger_status: str  # 항상 "draft"
    auto_trade_enabled: bool  # 항상 False
    proposal_status: str  # 항상 "pending" (승인 아님)
    no_change: bool
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "source_analysis_run_id": self.source_analysis_run_id,
            "source_session_id": self.source_session_id,
            "base_version_id": self.base_version_id,
            "challenger_version_id": self.challenger_version_id,
            "challenger_status": self.challenger_status,
            "auto_trade_enabled": self.auto_trade_enabled,
            "proposal_status": self.proposal_status,
            "no_change": self.no_change,
            "warnings": self.warnings,
        }


class PaperSignalChallengerService:
    """paper_signal_analysis 제안에서 DRAFT-only challenger 버전을 준비한다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._proposal_repo = StrategyProposalRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._run_repo = AiAnalysisRunRepository(session)
        self._strategy_service = StrategyService(session)

    async def prepare_from_proposal(
        self,
        proposal_id: int,
        confirmed: bool,
        confirmed_by: str | None,
    ) -> ChallengerPreparation:
        # --- 확인 게이트 ---
        if not confirmed:
            raise ConfirmationRequiredError("confirmed must be true")
        if not confirmed_by:
            raise ConfirmationRequiredError("confirmed_by is required")

        # --- 제안 로드 + 자격 검증 ---
        proposal = await self._proposal_repo.get(proposal_id)
        if proposal is None:
            raise ChallengerProposalNotFoundError(proposal_id)
        if proposal.source != SIGNAL_TRACK_SOURCE:
            raise NotSignalProposalError(
                f"proposal {proposal_id} source is {proposal.source!r}, "
                f"not {SIGNAL_TRACK_SOURCE!r}"
            )
        if proposal.status != ProposalStatus.PENDING:
            raise ProposalNotPendingError(
                f"proposal {proposal_id} status is {proposal.status.value}, not pending"
            )
        # 중복 준비 방지 — 이미 challenger 버전이 연결돼 있으면 409.
        if proposal.created_version_id is not None:
            raise ChallengerAlreadyPreparedError(
                f"proposal {proposal_id} already has created_version_id "
                f"{proposal.created_version_id}"
            )

        # ai_analysis_run_id + run target_type 검증.
        if proposal.ai_analysis_run_id is None:
            raise MissingAnalysisRunError(
                f"proposal {proposal_id} has no ai_analysis_run_id"
            )
        run = await self._run_repo.get(proposal.ai_analysis_run_id)
        if run is None:
            raise MissingAnalysisRunError(
                f"ai_analysis_run {proposal.ai_analysis_run_id} not found"
            )
        if run.target_type != AnalysisTargetType.PAPER_SIGNAL_SESSION:
            raise MissingAnalysisRunError(
                f"run {run.id} target_type is {run.target_type.value}, "
                f"not paper_signal_session"
            )

        # base_version_id + 버전 검증(동일 strategy_id 소속).
        if proposal.base_version_id is None:
            raise MissingBaseVersionError(
                f"proposal {proposal_id} has no base_version_id"
            )
        base = await self._version_repo.get(proposal.base_version_id)
        if base is None:
            raise MissingBaseVersionError(
                f"base strategy_version {proposal.base_version_id} not found"
            )
        if base.strategy_id != proposal.strategy_id:
            raise MissingBaseVersionError(
                f"base version {base.id} belongs to strategy {base.strategy_id}, "
                f"not proposal strategy {proposal.strategy_id}"
            )

        # --- 파라미터 안전 병합: base 위에 suggested를 덮어쓴다(required base 필드 보존) ---
        base_params = dict(base.parameters or {})
        suggested = dict(proposal.suggested_parameters or {})
        warnings: list[str] = []

        # auto_trade_enabled는 제안 내용과 무관하게 항상 False로 강제.
        if suggested.get("auto_trade_enabled") is True:
            warnings.append(
                "proposal requested auto_trade_enabled=true; overridden to false."
            )
        params = {**base_params, **suggested}
        params["auto_trade_enabled"] = False

        # 검증: strategy_type이 등록돼 있어야 한다(필수 필드 제거/무효화 방지).
        strategy_type = params.get("strategy_type")
        if strategy_type not in registered_types():
            raise InvalidChallengerParamsError(
                f"merged parameters.strategy_type {strategy_type!r} is not registered. "
                f"registered: {sorted(registered_types())}"
            )

        # 무변경(현재 버전 파라미터와 동일) 여부 — auto_trade_enabled 제외하고 비교.
        meaningful = compute_diff(
            {k: v for k, v in base_params.items() if k != "auto_trade_enabled"},
            {k: v for k, v in params.items() if k != "auto_trade_enabled"},
        )
        no_change = len(meaningful) == 0
        if no_change:
            warnings.append(
                "no parameter change vs base version; DRAFT challenger is a reviewable clone."
            )

        # --- DRAFT 버전 생성(approve 미호출, TESTING 아님) ---
        change_desc = (
            f"Signal challenger (DRAFT) prepared by {confirmed_by} "
            f"from paper_signal proposal #{proposal.id} "
            f"(auto_trade=false, runner-ineligible)"
        )
        version = await self._strategy_service.create_version(
            proposal.strategy_id,
            parameters=params,
            change_description=change_desc,
            status=StrategyVersionStatus.DRAFT,
        )

        # 추적 링크만 — 상태는 PENDING 유지(승인 아님), review 필드 미설정.
        proposal.created_version_id = version.id
        await self._session.commit()

        return ChallengerPreparation(
            proposal_id=proposal.id,
            source_analysis_run_id=proposal.ai_analysis_run_id,
            source_session_id=run.target_id,
            base_version_id=base.id,
            challenger_version_id=version.id,
            challenger_status=version.status.value,
            auto_trade_enabled=bool(params["auto_trade_enabled"]),
            proposal_status=proposal.status.value,
            no_change=no_change,
            warnings=warnings,
        )


def is_signal_track_proposal(source: str | None) -> bool:
    """source가 paper_signal 트랙(공유 approve 금지 대상)인지."""
    return source == SIGNAL_TRACK_SOURCE


__all__ = [
    "PaperSignalChallengerService",
    "ChallengerPreparation",
    "SIGNAL_TRACK_SOURCE",
    "is_signal_track_proposal",
    "ChallengerProposalNotFoundError",
    "ConfirmationRequiredError",
    "NotSignalProposalError",
    "MissingAnalysisRunError",
    "MissingBaseVersionError",
    "InvalidChallengerParamsError",
    "ProposalNotPendingError",
    "ChallengerAlreadyPreparedError",
]
