from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.repositories.strategy import StrategyRepository, StrategyVersionRepository


class StrategyNotFoundError(Exception):
    """해당 strategy_id의 Strategy가 존재하지 않을 때 발생."""


class StrategyVersionNotFoundError(Exception):
    """해당 strategy_id 하위에 version_id의 StrategyVersion이 존재하지 않을 때 발생."""


class StrategyService:
    """전략(Strategy)/전략 버전(StrategyVersion) 생성·조회·상태 변경을 담당한다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._strategy_repo = StrategyRepository(session)
        self._version_repo = StrategyVersionRepository(session)

    async def list_strategies(self) -> list[tuple[Strategy, int]]:
        return await self._strategy_repo.list_with_version_counts()

    async def create_strategy(self, name: str, description: str | None = None) -> Strategy:
        strategy = await self._strategy_repo.create(name=name, description=description)
        await self._session.commit()
        return strategy

    async def list_versions(self, strategy_id: int) -> list[StrategyVersion]:
        strategy = await self._strategy_repo.get(strategy_id)
        if strategy is None:
            raise StrategyNotFoundError(strategy_id)
        return await self._version_repo.list_by_strategy(strategy_id)

    async def create_version(
        self,
        strategy_id: int,
        parameters: dict,
        change_description: str | None = None,
        status: StrategyVersionStatus = StrategyVersionStatus.DRAFT,
    ) -> StrategyVersion:
        strategy = await self._strategy_repo.get(strategy_id)
        if strategy is None:
            raise StrategyNotFoundError(strategy_id)

        next_version_no = await self._version_repo.get_max_version_no(strategy_id) + 1
        version = await self._version_repo.create(
            strategy_id=strategy_id,
            version_no=next_version_no,
            parameters=parameters,
            change_description=change_description,
            status=status,
        )
        await self._session.commit()
        return version

    async def update_version(self, strategy_id: int, version_id: int, **fields: Any) -> StrategyVersion:
        version = await self._version_repo.get(version_id)
        if version is None or version.strategy_id != strategy_id:
            raise StrategyVersionNotFoundError(version_id)

        await self._version_repo.update(version, **fields)
        await self._session.commit()
        return version
