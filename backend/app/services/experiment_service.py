from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ExperimentStatus, MarketCode, VariantRole
from app.domain.models.experiment import Experiment, ExperimentVariant
from app.domain.repositories.experiment import (
    ExperimentRepository,
    ExperimentResultRepository,
    ExperimentVariantRepository,
)
from app.domain.repositories.strategy import StrategyVersionRepository
from app.domain.repositories.trade import TradeRepository
from app.trading.experiment.metrics import VariantMetrics, compute_metrics


class ExperimentNotFoundError(Exception):
    """experiment_id가 존재하지 않을 때 발생."""


class InvalidVariantError(Exception):
    """variant로 추가하려는 strategy_version이 존재하지 않을 때 발생."""


@dataclass
class VariantComparison:
    variant_id: int
    strategy_version_id: int
    role: VariantRole
    label: str | None
    metrics: VariantMetrics


@dataclass
class ComparisonResult:
    experiment_id: int
    variants: list[VariantComparison]
    winner_variant_id: int | None  # 기대값(expectancy)이 가장 높은 variant (거래 있는 것 중)


class ExperimentService:
    """전략 버전 비교 paper 실험을 관리하고, 체결 기반 성과를 비교한다 (C-2.26).

    성과는 각 variant의 strategy_version이 생성한 trade의 pnl로 계산한다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._experiment_repo = ExperimentRepository(session)
        self._variant_repo = ExperimentVariantRepository(session)
        self._result_repo = ExperimentResultRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._trade_repo = TradeRepository(session)

    async def create_experiment(
        self,
        name: str,
        market: MarketCode = MarketCode.KR,
        description: str | None = None,
    ) -> Experiment:
        experiment = await self._experiment_repo.create(
            name=name, market=market, description=description
        )
        await self._session.commit()
        return experiment

    async def list_experiments(self, market: MarketCode | None = None) -> list[Experiment]:
        return await self._experiment_repo.list_all(market=market)

    async def get_experiment(self, experiment_id: int) -> Experiment | None:
        return await self._experiment_repo.get_with_variants(experiment_id)

    async def update_status(
        self, experiment_id: int, status: ExperimentStatus
    ) -> Experiment:
        experiment = await self._experiment_repo.get(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        await self._experiment_repo.update(experiment, status=status)
        await self._session.commit()
        return experiment

    async def add_variant(
        self,
        experiment_id: int,
        strategy_version_id: int,
        role: VariantRole = VariantRole.CHALLENGER,
        label: str | None = None,
    ) -> ExperimentVariant:
        experiment = await self._experiment_repo.get(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        version = await self._version_repo.get(strategy_version_id)
        if version is None:
            raise InvalidVariantError(strategy_version_id)

        variant = await self._variant_repo.create(
            experiment_id=experiment_id,
            strategy_version_id=strategy_version_id,
            role=role,
            label=label,
        )
        await self._session.commit()
        return variant

    async def _variant_pnls(self, strategy_version_id: int) -> list[Decimal]:
        """variant의 strategy_version이 생성한 체결의 pnl을 시간순으로 반환한다."""
        trades = await self._trade_repo.list_by_strategy_version(strategy_version_id)
        # list_by_strategy_version은 created_at 내림차순 → 시간순으로 뒤집는다.
        chronological = list(reversed(trades))
        return [t.pnl_amount for t in chronological if t.pnl_amount is not None]

    async def compare(
        self, experiment_id: int, persist: bool = False
    ) -> ComparisonResult:
        """실험의 각 variant 성과를 계산하고 비교한다.

        persist=True이면 결과를 experiment_results 스냅샷으로 저장한다.
        """
        experiment = await self._experiment_repo.get(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)

        variants = await self._variant_repo.list_by_experiment(experiment_id)
        comparisons: list[VariantComparison] = []
        for v in variants:
            pnls = await self._variant_pnls(v.strategy_version_id)
            metrics = compute_metrics(pnls)
            comparisons.append(
                VariantComparison(
                    variant_id=v.id,
                    strategy_version_id=v.strategy_version_id,
                    role=v.role,
                    label=v.label,
                    metrics=metrics,
                )
            )
            if persist:
                await self._result_repo.create(
                    experiment_variant_id=v.id,
                    trades_count=metrics.trades_count,
                    win_rate=metrics.win_rate,
                    avg_profit=metrics.avg_profit,
                    avg_loss=metrics.avg_loss,
                    profit_factor=metrics.profit_factor,
                    expectancy=metrics.expectancy,
                    max_drawdown=metrics.max_drawdown,
                    metrics=metrics.to_dict(),
                )

        if persist:
            await self._session.commit()

        winner = self._pick_winner(comparisons)
        return ComparisonResult(
            experiment_id=experiment_id,
            variants=comparisons,
            winner_variant_id=winner,
        )

    @staticmethod
    def _pick_winner(comparisons: list[VariantComparison]) -> int | None:
        """거래가 있는 variant 중 기대값이 가장 높은 것을 선택한다(동률/무거래면 None)."""
        with_trades = [c for c in comparisons if c.metrics.trades_count > 0]
        if not with_trades:
            return None
        best = max(with_trades, key=lambda c: c.metrics.expectancy)
        # 동률(기대값 동일)이 둘 이상이면 승자 없음
        top = [c for c in with_trades if c.metrics.expectancy == best.metrics.expectancy]
        if len(top) > 1:
            return None
        return best.variant_id
