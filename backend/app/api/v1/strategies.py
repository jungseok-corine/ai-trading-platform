from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.strategy_analysis_input_service import StrategyAnalysisInputService
from app.services.strategy_performance_service import StrategyPerformanceService
from app.services.strategy_service import (
    StrategyNotFoundError,
    StrategyService,
    StrategyVersionNotFoundError,
)
from app.trading.strategy.schemas import (
    StrategyAnalysisInputRead,
    StrategyCreateRequest,
    StrategyRead,
    StrategyVersionCreateRequest,
    StrategyVersionPerformanceRead,
    StrategyVersionRead,
    StrategyVersionUpdateRequest,
)

router = APIRouter(prefix="/strategies", tags=["strategies"])


def get_strategy_service(session: AsyncSession = Depends(get_db)) -> StrategyService:
    return StrategyService(session)


def get_performance_service(session: AsyncSession = Depends(get_db)) -> StrategyPerformanceService:
    return StrategyPerformanceService(session)


def get_analysis_input_service(
    session: AsyncSession = Depends(get_db),
) -> StrategyAnalysisInputService:
    return StrategyAnalysisInputService(session)


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


@router.get(
    "/{strategy_id}/versions/{version_id}/performance",
    response_model=StrategyVersionPerformanceRead,
)
async def get_version_performance(
    strategy_id: int,
    version_id: int,
    service: StrategyPerformanceService = Depends(get_performance_service),
) -> StrategyVersionPerformanceRead:
    """strategy_version의 신호 기반 성과와 실제 체결 성과를 반환한다.

    신호가 없으면 빈 집계(zeros)를 반환한다.
    strategy_id/version_id 조합이 없으면 404.
    """
    performance = await service.get_version_performance(strategy_id, version_id)
    if performance is None:
        raise HTTPException(status_code=404, detail="strategy version not found")
    return performance


@router.get(
    "/{strategy_id}/versions/{version_id}/analysis-input",
    response_model=StrategyAnalysisInputRead,
)
async def get_analysis_input(
    strategy_id: int,
    version_id: int,
    service: StrategyAnalysisInputService = Depends(get_analysis_input_service),
) -> StrategyAnalysisInputRead:
    """LLM에 바로 넘길 수 있는 strategy_version 분석 입력 payload를 반환한다.

    strategy_id/version_id 조합이 없으면 404.
    데이터(신호, market_data, 실제 거래)가 없어도 payload는 항상 생성된다.
    """
    result = await service.get_analysis_input(strategy_id, version_id)
    if result is None:
        raise HTTPException(status_code=404, detail="strategy version not found")
    return result


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
