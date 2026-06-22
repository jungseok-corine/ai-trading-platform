from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.watchlist_service import (
    DuplicateWatchlistSymbolError,
    WatchlistNotFoundError,
    WatchlistService,
    WatchlistStrategyNotFoundError,
    WatchlistSymbolNotFoundError,
)
from app.trading.strategy.schemas import (
    WatchlistBulkStrategyCreateItem,
    WatchlistBulkStrategyCreateRequest,
    WatchlistBulkStrategyCreateResponse,
    WatchlistCreateRequest,
    WatchlistRead,
    WatchlistSymbolCreateRequest,
    WatchlistSymbolRead,
    WatchlistSymbolUpdateRequest,
)

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


def get_watchlist_service(session: AsyncSession = Depends(get_db)) -> WatchlistService:
    return WatchlistService(session)


@router.get("", response_model=list[WatchlistRead])
async def list_watchlists(service: WatchlistService = Depends(get_watchlist_service)) -> list[WatchlistRead]:
    pairs = await service.list_watchlists()
    return [
        WatchlistRead(
            id=watchlist.id,
            name=watchlist.name,
            description=watchlist.description,
            enabled=watchlist.enabled,
            symbol_count=count,
            created_at=watchlist.created_at,
            updated_at=watchlist.updated_at,
        )
        for watchlist, count in pairs
    ]


@router.post("", response_model=WatchlistRead)
async def create_watchlist(
    payload: WatchlistCreateRequest,
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistRead:
    watchlist = await service.create_watchlist(payload.name, payload.description, payload.enabled)
    return WatchlistRead(
        id=watchlist.id,
        name=watchlist.name,
        description=watchlist.description,
        enabled=watchlist.enabled,
        symbol_count=0,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


@router.get("/{watchlist_id}/symbols", response_model=list[WatchlistSymbolRead])
async def list_watchlist_symbols(
    watchlist_id: int,
    service: WatchlistService = Depends(get_watchlist_service),
) -> list[WatchlistSymbolRead]:
    try:
        return await service.list_symbols(watchlist_id)
    except WatchlistNotFoundError as e:
        raise HTTPException(status_code=404, detail="watchlist not found") from e


@router.post("/{watchlist_id}/symbols", response_model=WatchlistSymbolRead)
async def add_watchlist_symbol(
    watchlist_id: int,
    payload: WatchlistSymbolCreateRequest,
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistSymbolRead:
    try:
        return await service.add_symbol(
            watchlist_id,
            symbol_code=payload.symbol_code,
            symbol_name=payload.symbol_name,
            market=payload.market,
            exchange=payload.exchange,
            enabled=payload.enabled,
            note=payload.note,
        )
    except WatchlistNotFoundError as e:
        raise HTTPException(status_code=404, detail="watchlist not found") from e
    except DuplicateWatchlistSymbolError as e:
        raise HTTPException(status_code=409, detail="symbol already exists in this watchlist") from e


@router.patch("/{watchlist_id}/symbols/{symbol_id}", response_model=WatchlistSymbolRead)
async def update_watchlist_symbol(
    watchlist_id: int,
    symbol_id: int,
    payload: WatchlistSymbolUpdateRequest,
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistSymbolRead:
    fields = payload.model_dump(exclude_unset=True)
    try:
        return await service.update_symbol(watchlist_id, symbol_id, **fields)
    except WatchlistSymbolNotFoundError as e:
        raise HTTPException(status_code=404, detail="watchlist symbol not found") from e


@router.delete("/{watchlist_id}/symbols/{symbol_id}", status_code=204)
async def delete_watchlist_symbol(
    watchlist_id: int,
    symbol_id: int,
    service: WatchlistService = Depends(get_watchlist_service),
) -> None:
    try:
        await service.delete_symbol(watchlist_id, symbol_id)
    except WatchlistSymbolNotFoundError as e:
        raise HTTPException(status_code=404, detail="watchlist symbol not found") from e


@router.post("/{watchlist_id}/create-strategy-versions", response_model=WatchlistBulkStrategyCreateResponse)
async def create_strategy_versions_from_watchlist(
    watchlist_id: int,
    payload: WatchlistBulkStrategyCreateRequest,
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistBulkStrategyCreateResponse:
    """Watchlist에 등록된 enabled 종목마다 strategy_version을 하나씩 생성한다.

    동일 strategy에 이미 같은 symbol_code의 버전이 있으면 생성을 건너뛰고 결과에 사유를 표시한다.
    auto_trade_enabled=true는 요청 자체에서 거부된다 (422).
    """
    try:
        results = await service.create_strategy_versions_bulk(
            watchlist_id,
            strategy_id=payload.strategy_id,
            short_window=payload.short_window,
            long_window=payload.long_window,
            timeframe=payload.timeframe,
            quantity=payload.quantity,
            account_id=payload.account_id,
            status=payload.status,
        )
    except WatchlistNotFoundError as e:
        raise HTTPException(status_code=404, detail="watchlist not found") from e
    except WatchlistStrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail="strategy not found") from e

    return WatchlistBulkStrategyCreateResponse(
        strategy_id=payload.strategy_id,
        items=[WatchlistBulkStrategyCreateItem(**item) for item in results],
    )
