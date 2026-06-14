from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.strategy import StrategyVersion
from app.domain.models.watchlist import Watchlist, WatchlistSymbol
from app.domain.repositories.strategy import StrategyRepository, StrategyVersionRepository
from app.domain.repositories.watchlist import WatchlistRepository, WatchlistSymbolRepository


class WatchlistNotFoundError(Exception):
    """해당 watchlist_id의 Watchlist가 존재하지 않을 때 발생."""


class WatchlistSymbolNotFoundError(Exception):
    """해당 watchlist_id 하위에 symbol_id의 WatchlistSymbol이 존재하지 않을 때 발생."""


class DuplicateWatchlistSymbolError(Exception):
    """동일 watchlist에 동일 symbol_code를 중복 등록하려 할 때 발생."""


class WatchlistStrategyNotFoundError(Exception):
    """bulk 생성 요청의 strategy_id에 해당하는 Strategy가 존재하지 않을 때 발생."""


class WatchlistService:
    """Watchlist/WatchlistSymbol 생성·조회·관리 및 Watchlist 기반 strategy_version 일괄 생성을 담당한다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._watchlist_repo = WatchlistRepository(session)
        self._symbol_repo = WatchlistSymbolRepository(session)
        self._strategy_repo = StrategyRepository(session)
        self._version_repo = StrategyVersionRepository(session)

    async def list_watchlists(self) -> list[tuple[Watchlist, int]]:
        return await self._watchlist_repo.list_with_symbol_counts()

    async def create_watchlist(
        self, name: str, description: str | None = None, enabled: bool = True
    ) -> Watchlist:
        watchlist = await self._watchlist_repo.create(name=name, description=description, enabled=enabled)
        await self._session.commit()
        return watchlist

    async def list_symbols(self, watchlist_id: int) -> list[WatchlistSymbol]:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None:
            raise WatchlistNotFoundError(watchlist_id)
        return await self._symbol_repo.list_by_watchlist(watchlist_id)

    async def add_symbol(
        self,
        watchlist_id: int,
        symbol_code: str,
        symbol_name: str | None = None,
        enabled: bool = True,
        note: str | None = None,
    ) -> WatchlistSymbol:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None:
            raise WatchlistNotFoundError(watchlist_id)

        existing = await self._symbol_repo.get_by_symbol_code(watchlist_id, symbol_code)
        if existing is not None:
            raise DuplicateWatchlistSymbolError(symbol_code)

        symbol = await self._symbol_repo.create(
            watchlist_id=watchlist_id,
            symbol_code=symbol_code,
            symbol_name=symbol_name,
            enabled=enabled,
            note=note,
        )
        await self._session.commit()
        return symbol

    async def update_symbol(self, watchlist_id: int, symbol_id: int, **fields: Any) -> WatchlistSymbol:
        symbol = await self._symbol_repo.get(symbol_id)
        if symbol is None or symbol.watchlist_id != watchlist_id:
            raise WatchlistSymbolNotFoundError(symbol_id)

        await self._symbol_repo.update(symbol, **fields)
        await self._session.commit()
        return symbol

    async def delete_symbol(self, watchlist_id: int, symbol_id: int) -> None:
        symbol = await self._symbol_repo.get(symbol_id)
        if symbol is None or symbol.watchlist_id != watchlist_id:
            raise WatchlistSymbolNotFoundError(symbol_id)

        await self._symbol_repo.delete(symbol)
        await self._session.commit()

    async def create_strategy_versions_bulk(
        self,
        watchlist_id: int,
        strategy_id: int,
        short_window: int,
        long_window: int,
        timeframe: str,
        quantity: int,
        account_id: int | None,
        status: StrategyVersionStatus,
    ) -> list[dict[str, Any]]:
        """Watchlist에서 enabled=true인 종목마다 strategy_version을 하나씩 생성한다.

        동일 strategy_id에 동일 symbol_code의 버전이 이미 존재하면 생성을 건너뛰고
        기존 버전 id와 사유를 결과에 포함한다 (중복 생성 방지).
        auto_trade_enabled는 항상 false로 생성되며, 자동매매는 개별 전략 버전 화면에서
        하나씩 켜야 한다.
        """
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None:
            raise WatchlistNotFoundError(watchlist_id)

        strategy = await self._strategy_repo.get(strategy_id)
        if strategy is None:
            raise WatchlistStrategyNotFoundError(strategy_id)

        symbols = await self._symbol_repo.list_by_watchlist(watchlist_id)
        existing_versions = await self._version_repo.list_by_strategy(strategy_id)
        existing_by_symbol: dict[str, StrategyVersion] = {}
        for version in existing_versions:
            symbol_code = (version.parameters or {}).get("symbol_code")
            if symbol_code is not None and symbol_code not in existing_by_symbol:
                existing_by_symbol[symbol_code] = version

        results: list[dict[str, Any]] = []
        for symbol in symbols:
            if not symbol.enabled:
                continue

            duplicate = existing_by_symbol.get(symbol.symbol_code)
            if duplicate is not None:
                results.append(
                    {
                        "symbol_code": symbol.symbol_code,
                        "symbol_name": symbol.symbol_name,
                        "created": False,
                        "strategy_version_id": duplicate.id,
                        "reason": "duplicate_symbol_version_exists",
                    }
                )
                continue

            next_version_no = await self._version_repo.get_max_version_no(strategy_id) + 1
            parameters = {
                "strategy_type": "moving_average_cross",
                "symbol_code": symbol.symbol_code,
                "short_window": short_window,
                "long_window": long_window,
                "quantity": quantity,
                "timeframe": timeframe,
                "account_id": account_id,
                "enabled": True,
                "auto_trade_enabled": False,
            }
            version = await self._version_repo.create(
                strategy_id=strategy_id,
                version_no=next_version_no,
                parameters=parameters,
                change_description=f"Watchlist '{watchlist.name}' 기반 일괄 생성",
                status=status,
            )
            existing_by_symbol[symbol.symbol_code] = version
            results.append(
                {
                    "symbol_code": symbol.symbol_code,
                    "symbol_name": symbol.symbol_name,
                    "created": True,
                    "strategy_version_id": version.id,
                    "reason": None,
                }
            )

        await self._session.commit()
        return results
