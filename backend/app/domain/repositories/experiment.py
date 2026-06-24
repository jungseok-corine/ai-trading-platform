from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.domain.models.enums import ExperimentStatus, MarketCode
from app.domain.models.experiment import (
    Experiment,
    ExperimentResult,
    ExperimentVariant,
)
from app.domain.repositories.base import BaseRepository


class ExperimentRepository(BaseRepository[Experiment]):
    model = Experiment

    async def get_with_variants(self, experiment_id: int) -> Experiment | None:
        result = await self.session.execute(
            select(Experiment)
            .where(Experiment.id == experiment_id)
            .options(selectinload(Experiment.variants))
        )
        return result.scalar_one_or_none()

    async def list_all(self, market: MarketCode | None = None) -> list[Experiment]:
        stmt = select(Experiment).order_by(Experiment.id.desc())
        if market is not None:
            stmt = stmt.where(Experiment.market == market)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ExperimentVariantRepository(BaseRepository[ExperimentVariant]):
    model = ExperimentVariant

    async def list_by_experiment(self, experiment_id: int) -> list[ExperimentVariant]:
        result = await self.session.execute(
            select(ExperimentVariant)
            .where(ExperimentVariant.experiment_id == experiment_id)
            .order_by(ExperimentVariant.id)
        )
        return list(result.scalars().all())

    async def exists(self, experiment_id: int, strategy_version_id: int) -> bool:
        result = await self.session.execute(
            select(ExperimentVariant.id).where(
                ExperimentVariant.experiment_id == experiment_id,
                ExperimentVariant.strategy_version_id == strategy_version_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_running_for_strategy_version(
        self, strategy_version_id: int
    ) -> list[ExperimentVariant]:
        """RUNNING 상태 실험에서 이 strategy_version을 사용하는 variant 목록을 반환한다.

        반환된 버전들은 archive/status 변경 대상에서 제외해야 한다(안전 보호).
        """
        result = await self.session.execute(
            select(ExperimentVariant)
            .join(Experiment, ExperimentVariant.experiment_id == Experiment.id)
            .where(
                ExperimentVariant.strategy_version_id == strategy_version_id,
                Experiment.status == ExperimentStatus.RUNNING,
            )
        )
        return list(result.scalars().all())


class ExperimentResultRepository(BaseRepository[ExperimentResult]):
    model = ExperimentResult
