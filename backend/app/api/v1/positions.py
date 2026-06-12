from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client
from app.db.session import get_db
from app.domain.repositories.position import PositionRepository
from app.domain.repositories.position_event import PositionEventRepository
from app.services.portfolio_service import PortfolioService
from app.services.position_service import PositionService
from app.trading.broker.base import BrokerClient
from app.trading.position.schemas import (
    BrokerSyncResultRead,
    PortfolioSummaryRead,
    PositionEventRead,
    PositionRead,
    RefreshPricesResultRead,
)

router = APIRouter(tags=["positions"])


def get_position_service(
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
) -> PositionService:
    return PositionService(session, broker)


@router.get("/positions", response_model=list[PositionRead])
async def list_positions(
    account_id: int | None = None,
    session: AsyncSession = Depends(get_db),
) -> list[PositionRead]:
    repo = PositionRepository(session)
    return await repo.list_by_account(account_id=account_id)


@router.post("/positions/refresh-prices", response_model=RefreshPricesResultRead)
async def refresh_all_position_prices(
    account_id: int,
    service: PositionService = Depends(get_position_service),
) -> RefreshPricesResultRead:
    positions = await service.refresh_all_prices(account_id)
    return RefreshPricesResultRead(updated=len(positions), positions=list(positions))


@router.post("/positions/sync-from-broker", response_model=BrokerSyncResultRead)
async def sync_positions_from_broker(
    account_id: int,
    service: PositionService = Depends(get_position_service),
) -> BrokerSyncResultRead:
    result = await service.sync_from_broker_positions(account_id)
    return BrokerSyncResultRead(
        created=result.created,
        updated=result.updated,
        zeroed=result.zeroed,
        positions=list(result.positions),
    )


@router.get("/portfolio/summary", response_model=PortfolioSummaryRead)
async def get_portfolio_summary(
    account_id: int,
    session: AsyncSession = Depends(get_db),
) -> PortfolioSummaryRead:
    return await PortfolioService(session).get_summary(account_id)


@router.post("/positions/{position_id}/refresh-price", response_model=PositionRead)
async def refresh_position_price(
    position_id: int,
    service: PositionService = Depends(get_position_service),
) -> PositionRead:
    position = await service.refresh_last_price(position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="position not found")
    return position


@router.get("/positions/{position_id}/events", response_model=list[PositionEventRead])
async def list_position_events(
    position_id: int,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
) -> list[PositionEventRead]:
    repo = PositionEventRepository(session)
    return await repo.list_by_position(position_id, limit=limit, offset=offset)


@router.get("/positions/{account_id}/{symbol_code}", response_model=PositionRead)
async def get_position(
    account_id: int,
    symbol_code: str,
    session: AsyncSession = Depends(get_db),
) -> PositionRead:
    repo = PositionRepository(session)
    position = await repo.get_by_account_symbol(account_id, symbol_code)
    if position is None:
        raise HTTPException(status_code=404, detail="position not found")
    return position
