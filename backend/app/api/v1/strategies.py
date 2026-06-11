from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.strategy_service import (
    StrategyNotFoundError,
    StrategyService,
    StrategyVersionNotFoundError,
)
from app.trading.strategy.schemas import (
    StrategyCreateRequest,
    StrategyRead,
    StrategyVersionCreateRequest,
    StrategyVersionRead,
    StrategyVersionUpdateRequest,
)

router = APIRouter(prefix="/strategies", tags=["strategies"])


def get_strategy_service(session: AsyncSession = Depends(get_db)) -> StrategyService:
    return StrategyService(session)


@router.get("", response_model=list[StrategyRead])
async def list_strategies(service: StrategyService = Depends(get_strategy_service)) -> list[StrategyRead]:
    pairs = await service.list_strategies()
    return [
        StrategyRead(
            id=strategy.id,
            name=strategy.name,
            description=strategy.description,
            created_at=strategy.created_at,
            version_count=count,
        )
        for strategy, count in pairs
    ]


@router.post("", response_model=StrategyRead)
async def create_strategy(
    payload: StrategyCreateRequest,
    service: StrategyService = Depends(get_strategy_service),
) -> StrategyRead:
    strategy = await service.create_strategy(payload.name, payload.description)
    return StrategyRead(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        created_at=strategy.created_at,
        version_count=0,
    )


@router.get("/{strategy_id}/versions", response_model=list[StrategyVersionRead])
async def list_strategy_versions(
    strategy_id: int,
    service: StrategyService = Depends(get_strategy_service),
) -> list[StrategyVersionRead]:
    try:
        return await service.list_versions(strategy_id)
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail="strategy not found") from e


@router.post("/{strategy_id}/versions", response_model=StrategyVersionRead)
async def create_strategy_version(
    strategy_id: int,
    payload: StrategyVersionCreateRequest,
    service: StrategyService = Depends(get_strategy_service),
) -> StrategyVersionRead:
    try:
        return await service.create_version(
            strategy_id,
            parameters=payload.parameters.model_dump(),
            change_description=payload.change_description,
            status=payload.status,
        )
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail="strategy not found") from e


@router.patch("/{strategy_id}/versions/{version_id}", response_model=StrategyVersionRead)
async def update_strategy_version(
    strategy_id: int,
    version_id: int,
    payload: StrategyVersionUpdateRequest,
    service: StrategyService = Depends(get_strategy_service),
) -> StrategyVersionRead:
    fields = payload.model_dump(exclude_unset=True, exclude={"parameters"})
    if payload.parameters is not None:
        fields["parameters"] = payload.parameters.model_dump()
    try:
        return await service.update_version(strategy_id, version_id, **fields)
    except (StrategyNotFoundError, StrategyVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail="strategy version not found") from e
