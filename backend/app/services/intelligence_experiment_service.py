"""Intelligence 후보 기반 Paper 실험 자동화 서비스 (C-2.27).

APPROVED IntelligenceStrategyProposal을 paper 실험으로 materialize한다.

흐름:
  IntelligenceStrategyProposal(APPROVED)
  → materialize(proposal_id)
      1. Strategy 생성 (paper 전용, 일반 운영 전략과 구분)
      2. StrategyVersion(DRAFT, auto_trade_enabled=False, paper_only=True) 생성
      3. Experiment(RUNNING) 생성
      4. ExperimentVariant 연결 (CHALLENGER)
      5. proposal.experiment_id + materialized_at 기록
  → conclude(experiment_id)
      1. Experiment.status = COMPLETED
      2. Experiment.ended_at 기록
      3. ExperimentService.compare(persist=True) → ExperimentResult 저장

안전 원칙:
- StrategyVersion.status = DRAFT (ACTIVE 자동 생성 절대 금지)
- auto_trade_enabled = False (suggested_parameters에 True가 있어도 강제 override)
- 실전 계좌 연결 없음
- 주문 실행 없음 (paper experiment 메타데이터 관리만 수행)
- 실주문 TR_ID 없음
- C-2.28 이후 기능 없음
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import (
    ExperimentStatus,
    IntelligenceStrategyProposalStatus,
    MarketCode,
    StrategyVersionStatus,
    VariantRole,
)
from app.domain.models.experiment import Experiment
from app.domain.models.intelligence_strategy_proposal import IntelligenceStrategyProposal
from app.domain.repositories.experiment import (
    ExperimentRepository,
    ExperimentVariantRepository,
)
from app.domain.repositories.intelligence_strategy_proposal import (
    IntelligenceStrategyProposalRepository,
)
from app.domain.repositories.strategy import StrategyRepository, StrategyVersionRepository
from app.domain.repositories.trade import TradeRepository
from app.services.experiment_service import ComparisonResult, ExperimentNotFoundError, ExperimentService


class ProposalNotFoundError(Exception):
    pass


class ProposalNotApprovedError(Exception):
    """APPROVED 상태가 아닌 proposal을 materialize하려 할 때 발생."""


class AlreadyMaterializedError(Exception):
    """이미 materialize된 proposal을 재시도할 때 발생."""


class ExperimentAlreadyConcludedError(Exception):
    """이미 COMPLETED인 실험을 conclude하려 할 때 발생."""


@dataclass
class MaterializeResult:
    proposal_id: int
    strategy_id: int
    strategy_version_id: int
    experiment_id: int
    already_existed: bool = False


@dataclass
class StopConditionResult:
    experiment_id: int
    days_elapsed: int
    total_trades: int
    max_days_met: bool
    min_trades_met: bool
    can_conclude: bool

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "days_elapsed": self.days_elapsed,
            "total_trades": self.total_trades,
            "max_days_met": self.max_days_met,
            "min_trades_met": self.min_trades_met,
            "can_conclude": self.can_conclude,
        }


class IntelligenceExperimentService:
    """Intelligence 기반 paper 실험 materialize + conclude."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._proposal_repo = IntelligenceStrategyProposalRepository(session)
        self._strategy_repo = StrategyRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._experiment_repo = ExperimentRepository(session)
        self._variant_repo = ExperimentVariantRepository(session)
        self._trade_repo = TradeRepository(session)

    async def materialize(self, proposal_id: int) -> MaterializeResult:
        """APPROVED proposal → Strategy + StrategyVersion(DRAFT) + Experiment(RUNNING).

        - StrategyVersion.status = DRAFT (ACTIVE 아님)
        - auto_trade_enabled = False (강제, 예외 없음)
        - 중복 materialize: experiment_id가 이미 있으면 기존 결과 반환
        """
        proposal = await self._proposal_repo.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)

        if proposal.status != IntelligenceStrategyProposalStatus.APPROVED:
            raise ProposalNotApprovedError(
                f"proposal {proposal_id} is {proposal.status.value}, not approved"
            )

        # 중복 materialize 방지
        if proposal.experiment_id is not None:
            return MaterializeResult(
                proposal_id=proposal.id,
                strategy_id=0,
                strategy_version_id=0,
                experiment_id=proposal.experiment_id,
                already_existed=True,
            )

        # 1. Strategy 생성 (paper 전용)
        strategy_name = (
            f"Intelligence Experiment: {proposal.symbol_code} {proposal.suggested_strategy_type}"
        )
        strategy = await self._strategy_repo.create(
            name=strategy_name,
            description=(
                f"IntelligenceStrategyProposal #{proposal.id} 기반 paper 실험용 전략. "
                "일반 운영 전략과 분리. 실전 배치 금지."
            ),
        )

        # 2. StrategyVersion(DRAFT) 생성
        raw_params = dict(proposal.suggested_parameters or {})
        # auto_trade_enabled=True는 절대 허용하지 않는다.
        raw_params["auto_trade_enabled"] = False
        raw_params["strategy_type"] = proposal.suggested_strategy_type
        raw_params["symbol_code"] = proposal.symbol_code
        raw_params["origin"] = "intelligence_strategy_proposal"
        raw_params["proposal_id"] = proposal.id
        raw_params["candidate_id"] = proposal.intelligence_candidate_id
        raw_params["paper_only"] = True

        version = await self._version_repo.create(
            strategy_id=strategy.id,
            version_no=1,
            parameters=raw_params,
            change_description=(
                f"Intelligence 후보 기반 paper 실험용 버전 (proposal #{proposal.id})"
            ),
            status=StrategyVersionStatus.DRAFT,
        )

        # 3. Experiment(RUNNING) 생성
        now = datetime.now(timezone.utc)
        experiment = await self._experiment_repo.create(
            name=f"Intelligence: {proposal.symbol_code} {proposal.suggested_strategy_type}",
            market=proposal.market,
            description=(
                f"IntelligenceStrategyProposal #{proposal.id} 기반 paper 실험. "
                f"candidate_id={proposal.intelligence_candidate_id}"
            ),
            status=ExperimentStatus.RUNNING,
            started_at=now,
        )

        # 4. ExperimentVariant (CHALLENGER)
        await self._variant_repo.create(
            experiment_id=experiment.id,
            strategy_version_id=version.id,
            role=VariantRole.CHALLENGER,
            label=f"{proposal.suggested_strategy_type} v1",
        )

        # 5. proposal 연결
        proposal.experiment_id = experiment.id
        proposal.materialized_at = now
        await self._session.flush()
        await self._session.commit()

        return MaterializeResult(
            proposal_id=proposal.id,
            strategy_id=strategy.id,
            strategy_version_id=version.id,
            experiment_id=experiment.id,
            already_existed=False,
        )

    async def conclude(self, experiment_id: int) -> ComparisonResult:
        """RUNNING experiment → COMPLETED + ExperimentResult 저장."""
        experiment = await self._experiment_repo.get(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        if experiment.status == ExperimentStatus.COMPLETED:
            raise ExperimentAlreadyConcludedError(experiment_id)

        now = datetime.now(timezone.utc)
        await self._experiment_repo.update(
            experiment,
            status=ExperimentStatus.COMPLETED,
            ended_at=now,
        )

        exp_service = ExperimentService(self._session)
        result = await exp_service.compare(experiment_id, persist=True)
        return result

    async def check_stop_conditions(
        self,
        experiment_id: int,
        max_days: int = 7,
        min_trades: int = 20,
    ) -> StopConditionResult:
        """종료 조건 충족 여부 판단. max_days 또는 min_trades 중 하나라도 충족하면 can_conclude."""
        experiment = await self._experiment_repo.get(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)

        started_at = experiment.started_at or datetime.now(timezone.utc)
        days_elapsed = (datetime.now(timezone.utc) - started_at).days

        variants = await self._variant_repo.list_by_experiment(experiment_id)
        total_trades = 0
        for v in variants:
            total_trades += await self._trade_repo.count_by_strategy_version(v.strategy_version_id)

        max_days_met = days_elapsed >= max_days
        min_trades_met = total_trades >= min_trades

        return StopConditionResult(
            experiment_id=experiment_id,
            days_elapsed=days_elapsed,
            total_trades=total_trades,
            max_days_met=max_days_met,
            min_trades_met=min_trades_met,
            can_conclude=max_days_met or min_trades_met,
        )

    async def list_running_intelligence_experiments(self) -> list[Experiment]:
        """intelligence proposal에 연결된 RUNNING 실험 목록."""
        result = await self._session.execute(
            select(Experiment)
            .join(
                IntelligenceStrategyProposal,
                IntelligenceStrategyProposal.experiment_id == Experiment.id,
            )
            .where(Experiment.status == ExperimentStatus.RUNNING)
        )
        return list(result.scalars().all())

    async def autopilot_check(
        self,
        max_days: int = 7,
        min_trades: int = 20,
    ) -> dict:
        """RUNNING intelligence experiment를 점검해 종료 조건 충족 시 자동 conclude."""
        experiments = await self.list_running_intelligence_experiments()
        concluded = []
        skipped = []
        errors = []

        for exp in experiments:
            try:
                cond = await self.check_stop_conditions(
                    exp.id, max_days=max_days, min_trades=min_trades
                )
                if cond.can_conclude:
                    await self.conclude(exp.id)
                    concluded.append(exp.id)
                else:
                    skipped.append(exp.id)
            except Exception as exc:
                errors.append(f"experiment {exp.id}: {exc}")

        return {
            "checked": len(experiments),
            "concluded": concluded,
            "skipped": skipped,
            "errors": errors,
        }
