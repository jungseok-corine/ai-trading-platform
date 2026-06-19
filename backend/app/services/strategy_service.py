from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.repositories.signal_log import SignalLogRepository
from app.domain.repositories.strategy import StrategyRepository, StrategyVersionRepository
from app.domain.repositories.trade import TradeRepository


class StrategyNotFoundError(Exception):
    """해당 strategy_id의 Strategy가 존재하지 않을 때 발생."""


class StrategyVersionNotFoundError(Exception):
    """해당 strategy_id 하위에 version_id의 StrategyVersion이 존재하지 않을 때 발생."""


class StrategyVersionNotDeletableError(Exception):
    """삭제 정책상 hard delete가 허용되지 않는 버전을 삭제하려 할 때 발생.

    reason에 사람이 읽을 수 있는 사유(상태 또는 참조 데이터 존재)를 담는다.
    """

    def __init__(self, version_id: int, reason: str) -> None:
        self.version_id = version_id
        self.reason = reason
        super().__init__(f"strategy_version {version_id} is not deletable: {reason}")


class StrategyService:
    """전략(Strategy)/전략 버전(StrategyVersion) 생성·조회·상태 변경을 담당한다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._strategy_repo = StrategyRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._signal_log_repo = SignalLogRepository(session)
        self._trade_repo = TradeRepository(session)

    async def list_strategies(self) -> list[tuple[Strategy, int]]:
        return await self._strategy_repo.list_with_version_counts()

    async def create_strategy(self, name: str, description: str | None = None) -> Strategy:
        strategy = await self._strategy_repo.create(name=name, description=description)
        await self._session.commit()
        return strategy

    async def list_versions(
        self, strategy_id: int, include_archived: bool = False
    ) -> list[StrategyVersion]:
        strategy = await self._strategy_repo.get(strategy_id)
        if strategy is None:
            raise StrategyNotFoundError(strategy_id)
        return await self._version_repo.list_by_strategy(
            strategy_id, include_archived=include_archived
        )

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

    async def _get_owned_version(self, strategy_id: int, version_id: int) -> StrategyVersion:
        version = await self._version_repo.get(version_id)
        if version is None or version.strategy_id != strategy_id:
            raise StrategyVersionNotFoundError(version_id)
        return version

    async def _count_references(self, version_id: int) -> int:
        """version을 참조하는 signal_log/trade 개수의 합을 반환한다."""
        signals = await self._signal_log_repo.count_by_strategy_version(version_id)
        trades = await self._trade_repo.count_by_strategy_version(version_id)
        return signals + trades

    async def archive_version(self, strategy_id: int, version_id: int) -> StrategyVersion:
        """버전을 ARCHIVED 상태로 전환한다 (soft delete).

        어떤 상태/참조 여부와 무관하게 안전하게 보관 처리할 수 있다.
        """
        version = await self._get_owned_version(strategy_id, version_id)
        await self._version_repo.update(version, status=StrategyVersionStatus.ARCHIVED)
        await self._session.commit()
        return version

    async def delete_version(self, strategy_id: int, version_id: int) -> None:
        """버전을 hard delete 한다.

        삭제 정책 (C-2.21):
          - DRAFT 상태이고 참조 데이터(signal_log/trade)가 없을 때만 hard delete 허용.
          - 그 외(TESTING/ACTIVE/RETIRED/ARCHIVED 또는 참조 존재)는 archive를 사용해야 한다.
        정책 위반 시 StrategyVersionNotDeletableError를 발생시킨다.
        """
        version = await self._get_owned_version(strategy_id, version_id)

        if version.status != StrategyVersionStatus.DRAFT:
            raise StrategyVersionNotDeletableError(
                version_id,
                f"status가 {version.status.value}입니다. DRAFT만 삭제할 수 있으며, "
                "그 외에는 archive를 사용하세요.",
            )

        reference_count = await self._count_references(version_id)
        if reference_count > 0:
            raise StrategyVersionNotDeletableError(
                version_id,
                f"signal_log/trade {reference_count}건이 이 버전을 참조합니다. "
                "이력 보존을 위해 hard delete 대신 archive를 사용하세요.",
            )

        await self._version_repo.delete(version)
        await self._session.commit()
