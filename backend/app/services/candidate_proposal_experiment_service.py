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
