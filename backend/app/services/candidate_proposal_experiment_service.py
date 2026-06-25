"""APPROVED 후보 전략 제안 → Paper 실험 '준비' 서비스.

핵심: **준비는 실행이 아니다.** APPROVED 제안에 대해 사람이 명시적으로 액션할 때만,
DRAFT 상태의 paper 실험 골격을 만든다. 실험을 돌리지 않는다.

만드는 것:
  1. Strategy (paper 전용, 일반 운영 전략과 분리)
  2. StrategyVersion(status=DRAFT, auto_trade_enabled=False 강제)
  3. Experiment(status=DRAFT, started_at=None)   ← RUNNING 아님
  4. ExperimentVariant(CHALLENGER)
  5. proposal.experiment_id + prepared_at 기록 (idempotent 근거)

안전 불변식:
- StrategyVersion.status = DRAFT (ACTIVE/TESTING 아님 → runner의 list_active가 절대 안 잡음)
- auto_trade_enabled = False (suggested_parameters에 True가 있어도 강제 제거)
- Experiment.status = DRAFT (RUNNING 아님 → 실행/오토파일럿 대상 아님)
- 주문/체결/브로커 호출 없음, AssignmentService 호출 없음, 실전 계좌 연결 없음
- 이미 준비된 제안은 기존 결과를 반환(중복 생성 방지)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import (
    ExperimentStatus,
    MarketCode,
    StrategyVersionStatus,
    VariantRole,
)
from app.domain.repositories.candidate_event import CandidateEventRepository
from app.domain.repositories.candidate_strategy_proposal import (
    CandidateStrategyProposalRepository,
)
from app.domain.repositories.experiment import (
    ExperimentRepository,
    ExperimentVariantRepository,
)
from app.domain.repositories.strategy import StrategyRepository, StrategyVersionRepository


class ProposalNotFoundError(Exception):
    """candidate_strategy_proposal id가 존재하지 않을 때."""


class ProposalNotApprovedError(Exception):
    """APPROVED 상태가 아닌 제안을 준비하려 할 때(pending/rejected)."""


class ConfirmationRequiredError(Exception):
    """confirmed=true / confirmed_by 없이 활성화를 시도할 때."""


class NotPreparedError(Exception):
    """아직 paper 실험을 준비하지 않은 제안을 활성화하려 할 때."""


class InvalidExperimentStateError(Exception):
    """DRAFT가 아닌 실험을 활성화하려 할 때(COMPLETED/ARCHIVED 등)."""


class UnexpectedAutoTradeError(Exception):
    """연결된 전략 버전의 자동매매 토글이 켜져 있어 활성화를 거부할 때(방어적)."""


@dataclass
class PreparedExperiment:
    proposal_id: int
    candidate_event_id: int
    symbol_code: str
    suggested_strategy_type: str
    strategy_id: int | None
    strategy_version_id: int | None
    strategy_version_status: str
    experiment_id: int
    experiment_status: str
    auto_trade_enabled: bool  # 항상 False
    prepared_at: str | None
    already_prepared: bool


@dataclass
class ReadinessResult:
    """Paper 테스트 '준비 승인' 결과. 어떤 상태도 바꾸지 않는다(읽기 보존)."""

    proposal_id: int
    experiment_id: int
    experiment_status: str  # 항상 draft (변경 안 함)
    strategy_version_ids: list[int]
    strategy_version_statuses: list[str]  # 모두 draft (변경 안 함)
    auto_trade_enabled_values: list[bool]  # 모두 False
    ready: bool  # 항상 True (승인됨)
    already_ready: bool
    ready_at: str | None
    ready_by: str | None
    message: str


# 제안의 suggested_parameters에 준비 승인 메타를 남기는 키.
# prepare는 readiness 이전에 이미 끝났고(버전 생성 완료), runner는 StrategyVersion.parameters만
# 읽으므로 이 키는 실행에 절대 영향을 주지 않는다(전략 버전 파라미터로 새지 않음).
_READY_AT_KEY = "_paper_testing_ready_at"
_READY_BY_KEY = "_paper_testing_ready_by"


class CandidateProposalExperimentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._proposal_repo = CandidateStrategyProposalRepository(session)
        self._candidate_repo = CandidateEventRepository(session)
        self._strategy_repo = StrategyRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._experiment_repo = ExperimentRepository(session)
        self._variant_repo = ExperimentVariantRepository(session)

    async def prepare(
        self, proposal_id: int, created_by: str = "manual_user"
    ) -> PreparedExperiment:
        """APPROVED 제안 → DRAFT paper 실험 골격을 만든다(실행 아님). 이미 준비됐으면 기존 반환."""
        proposal = await self._proposal_repo.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)
        if proposal.status != "approved":
            raise ProposalNotApprovedError(
                f"proposal {proposal_id} is {proposal.status!r}, not approved"
            )

        # 중복 준비 방지(idempotent).
        if proposal.experiment_id is not None:
            exp = await self._experiment_repo.get(proposal.experiment_id)
            return PreparedExperiment(
                proposal_id=proposal.id,
                candidate_event_id=proposal.candidate_event_id,
                symbol_code=proposal.symbol_code,
                suggested_strategy_type=proposal.suggested_strategy_type,
                strategy_id=None,
                strategy_version_id=None,
                strategy_version_status=StrategyVersionStatus.DRAFT.value,
                experiment_id=proposal.experiment_id,
                experiment_status=(exp.status.value if exp else ExperimentStatus.DRAFT.value),
                auto_trade_enabled=False,
                prepared_at=proposal.prepared_at.isoformat() if proposal.prepared_at else None,
                already_prepared=True,
            )

        # 실험 market은 후보 이벤트의 market을 따른다(없으면 KR 기본).
        candidate = await self._candidate_repo.get(proposal.candidate_event_id)
        market = candidate.market if candidate is not None else MarketCode.KR

        # 1. Strategy (paper 전용)
        strategy = await self._strategy_repo.create(
            name=(
                f"Candidate Experiment: {proposal.symbol_code} "
                f"{proposal.suggested_strategy_type}"
            ),
            description=(
                f"CandidateStrategyProposal #{proposal.id} 기반 paper 실험 준비용 전략. "
                "일반 운영 전략과 분리. 실전 배치 금지."
            ),
        )

        # 2. StrategyVersion(DRAFT) — auto_trade_enabled는 무조건 False.
        params = dict(proposal.suggested_parameters or {})
        params["auto_trade_enabled"] = False
        params["strategy_type"] = proposal.suggested_strategy_type
        params["symbol_code"] = proposal.symbol_code
        params["origin"] = "candidate_strategy_proposal"
        params["proposal_id"] = proposal.id
        params["candidate_event_id"] = proposal.candidate_event_id
        params["paper_only"] = True
        version = await self._version_repo.create(
            strategy_id=strategy.id,
            version_no=1,
            parameters=params,
            change_description=(
                f"후보 제안 기반 paper 실험 준비용 버전 (proposal #{proposal.id}). 실행 아님."
            ),
            status=StrategyVersionStatus.DRAFT,
        )

        # 3. Experiment(DRAFT) — started_at 없음(아직 실행 안 함).
        experiment = await self._experiment_repo.create(
            name=f"Candidate: {proposal.symbol_code} {proposal.suggested_strategy_type}",
            market=market,
            description=(
                f"CandidateStrategyProposal #{proposal.id} 기반 준비된 paper 실험(DRAFT). "
                f"candidate_event_id={proposal.candidate_event_id}. 실행/주문 없음."
            ),
            status=ExperimentStatus.DRAFT,
        )

        # 4. ExperimentVariant (CHALLENGER)
        await self._variant_repo.create(
            experiment_id=experiment.id,
            strategy_version_id=version.id,
            role=VariantRole.CHALLENGER,
            label=f"{proposal.suggested_strategy_type} v1",
        )

        # 5. 제안에 연결 + 준비 시각 기록.
        now = datetime.now(timezone.utc)
        await self._proposal_repo.update(
            proposal, experiment_id=experiment.id, prepared_at=now
        )
        await self._session.commit()

        return PreparedExperiment(
            proposal_id=proposal.id,
            candidate_event_id=proposal.candidate_event_id,
            symbol_code=proposal.symbol_code,
            suggested_strategy_type=proposal.suggested_strategy_type,
            strategy_id=strategy.id,
            strategy_version_id=version.id,
            strategy_version_status=StrategyVersionStatus.DRAFT.value,
            experiment_id=experiment.id,
            experiment_status=ExperimentStatus.DRAFT.value,
            auto_trade_enabled=False,
            prepared_at=now.isoformat(),
            already_prepared=False,
        )

    async def approve_paper_testing_readiness(
        self, proposal_id: int, confirmed: bool, confirmed_by: str | None
    ) -> ReadinessResult:
        """준비된 DRAFT 실험을 'paper 테스트 준비됨'으로 **승인 기록만** 한다.

        **어떤 상태도 바꾸지 않는다(non-runnable 유지) — 실행/자동매매/주문이 아니다.**
        - StrategyVersion.status = DRAFT 유지 (runner의 list_active가 절대 안 잡음 → 신호 생성 없음).
        - Experiment.status = DRAFT 유지, started_at = null 유지.
        - 승인 사실만 제안의 suggested_parameters에 메타로 남긴다(_paper_testing_ready_*).
          이 키는 prepare 이후에 기록되며 StrategyVersion 파라미터로 새지 않아 실행과 무관하다.
        - confirmed=true + confirmed_by 필수. 이미 승인됐으면 idempotent.
        - StrategyVersion ACTIVE/TESTING 전환 없음, Experiment RUNNING 전환 없음, started_at 변경
          없음, 주문/체결/브로커/AssignmentService 호출 없음, scheduler/job 없음.
        - 실제 paper 신호 기록 시작(runner 대상화)은 **다음 작업**으로 분리한다.
        """
        if not confirmed:
            raise ConfirmationRequiredError("confirmed must be true")
        if not confirmed_by:
            raise ConfirmationRequiredError("confirmed_by is required")

        proposal = await self._proposal_repo.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)
        if proposal.status != "approved":
            raise ProposalNotApprovedError(
                f"proposal {proposal_id} is {proposal.status!r}, not approved"
            )
        if proposal.experiment_id is None:
            raise NotPreparedError(
                f"proposal {proposal_id} has no prepared experiment — prepare first"
            )

        experiment = await self._experiment_repo.get(proposal.experiment_id)
        if experiment is None:
            raise InvalidExperimentStateError(
                f"experiment {proposal.experiment_id} not found"
            )
        # 준비된(DRAFT) 실험에 대해서만 승인. 비-DRAFT(혹시라도)면 거부.
        if experiment.status != ExperimentStatus.DRAFT:
            raise InvalidExperimentStateError(
                f"experiment {experiment.id} is {experiment.status.value}, not draft"
            )

        variants = await self._variant_repo.list_by_experiment(experiment.id)
        version_ids = [v.strategy_version_id for v in variants]
        versions = [await self._version_repo.get(vid) for vid in version_ids]
        versions = [v for v in versions if v is not None]

        # 방어적 가드: 연결된 버전은 모두 DRAFT여야 하고 자동매매 토글이 켜져 있으면 거부.
        for v in versions:
            if v.status != StrategyVersionStatus.DRAFT:
                raise InvalidExperimentStateError(
                    f"strategy_version {v.id} is {v.status.value}, not draft"
                )
            if (v.parameters or {}).get("auto_trade_enabled"):
                raise UnexpectedAutoTradeError(
                    f"strategy_version {v.id} has auto-trade enabled — refusing to approve"
                )

        params = dict(proposal.suggested_parameters or {})
        prior_ready_at = params.get(_READY_AT_KEY)

        def _result(ready_at: str | None, ready_by: str | None, already: bool) -> ReadinessResult:
            return ReadinessResult(
                proposal_id=proposal.id,
                experiment_id=experiment.id,
                experiment_status=experiment.status.value,  # draft (불변)
                strategy_version_ids=[v.id for v in versions],
                strategy_version_statuses=[v.status.value for v in versions],  # draft (불변)
                auto_trade_enabled_values=[
                    bool((v.parameters or {}).get("auto_trade_enabled", False)) for v in versions
                ],
                ready=True,
                already_ready=already,
                ready_at=ready_at,
                ready_by=ready_by,
                message=(
                    "Paper 테스트 준비 승인됨 — DRAFT 유지, 신호 기록 시작 아님, 자동매매/주문 없음. "
                    "실제 신호 기록 시작은 별도 단계입니다."
                ),
            )

        # 이미 승인됨 → idempotent(상태도 그대로).
        if prior_ready_at:
            return _result(prior_ready_at, params.get(_READY_BY_KEY), already=True)

        now_iso = datetime.now(timezone.utc).isoformat()
        params[_READY_AT_KEY] = now_iso
        params[_READY_BY_KEY] = confirmed_by
        # 제안에만 메타 기록 — StrategyVersion/Experiment는 일절 건드리지 않는다.
        await self._proposal_repo.update(proposal, suggested_parameters=params)
        await self._session.commit()
        return _result(now_iso, confirmed_by, already=False)
