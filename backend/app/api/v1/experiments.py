"""Paper 실험(Experiment) API (C-2.26).

전략 버전을 variant로 묶어 paper에서 비교한다(챔피언/챌린저). 성과는 체결(trade) pnl
기반으로 계산하며, 주문을 실행하지 않는다.
"""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import ExperimentStatus, MarketCode, VariantRole
from app.services.experiment_service import (
    ExperimentNotFoundError,
    ExperimentService,
    InvalidVariantError,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])


def get_service(session: AsyncSession = Depends(get_db)) -> ExperimentService:
    return ExperimentService(session)


# --- schemas ---------------------------------------------------------------
class ExperimentCreateRequest(BaseModel):
    name: str
    market: MarketCode = MarketCode.KR
    description: str | None = None


class VariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: int
    strategy_version_id: int
    role: VariantRole
    label: str | None
    created_at: datetime


class ExperimentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market: MarketCode
    name: str
    description: str | None
    status: ExperimentStatus
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime


class ExperimentDetailRead(ExperimentRead):
    variants: list[VariantRead]


class VariantCreateRequest(BaseModel):
    strategy_version_id: int
    role: VariantRole = VariantRole.CHALLENGER
    label: str | None = None


class StatusUpdateRequest(BaseModel):
    status: ExperimentStatus


class VariantMetricsRead(BaseModel):
    trades_count: int
    win_count: int
    loss_count: int
    win_rate: Decimal
    avg_profit: Decimal
    avg_loss: Decimal
    profit_factor: Decimal | None
    expectancy: Decimal
    max_drawdown: Decimal


class VariantComparisonRead(BaseModel):
    variant_id: int
    strategy_version_id: int
    role: VariantRole
    label: str | None
    metrics: VariantMetricsRead


class ComparisonRead(BaseModel):
    experiment_id: int
    variants: list[VariantComparisonRead]
    winner_variant_id: int | None


# --- endpoints -------------------------------------------------------------
@router.post("", response_model=ExperimentRead, status_code=201)
async def create_experiment(
    payload: ExperimentCreateRequest, service: ExperimentService = Depends(get_service)
) -> ExperimentRead:
    experiment = await service.create_experiment(
        payload.name, payload.market, payload.description
    )
    return ExperimentRead.model_validate(experiment)


@router.get("", response_model=list[ExperimentRead])
async def list_experiments(
    market: MarketCode | None = Query(default=None),
    service: ExperimentService = Depends(get_service),
) -> list[ExperimentRead]:
    experiments = await service.list_experiments(market=market)
    return [ExperimentRead.model_validate(e) for e in experiments]


@router.get("/{experiment_id}", response_model=ExperimentDetailRead)
async def get_experiment(
    experiment_id: int, service: ExperimentService = Depends(get_service)
) -> ExperimentDetailRead:
    experiment = await service.get_experiment(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return ExperimentDetailRead.model_validate(experiment)


@router.patch("/{experiment_id}", response_model=ExperimentRead)
async def update_experiment_status(
    experiment_id: int,
    payload: StatusUpdateRequest,
    service: ExperimentService = Depends(get_service),
) -> ExperimentRead:
    try:
        experiment = await service.update_status(experiment_id, payload.status)
    except ExperimentNotFoundError as e:
        raise HTTPException(status_code=404, detail="experiment not found") from e
    return ExperimentRead.model_validate(experiment)


@router.post("/{experiment_id}/variants", response_model=VariantRead, status_code=201)
async def add_variant(
    experiment_id: int,
    payload: VariantCreateRequest,
    service: ExperimentService = Depends(get_service),
) -> VariantRead:
    try:
        variant = await service.add_variant(
            experiment_id,
            strategy_version_id=payload.strategy_version_id,
            role=payload.role,
            label=payload.label,
        )
    except ExperimentNotFoundError as e:
        raise HTTPException(status_code=404, detail="experiment not found") from e
    except InvalidVariantError as e:
        raise HTTPException(status_code=422, detail="strategy version not found") from e
    return VariantRead.model_validate(variant)


@router.post("/{experiment_id}/compare", response_model=ComparisonRead)
async def compare_experiment(
    experiment_id: int,
    persist: bool = Query(default=False),
    service: ExperimentService = Depends(get_service),
) -> ComparisonRead:
    """각 variant의 성과(승률/기대값/손익비/낙폭)를 계산해 비교하고 승자를 반환한다."""
    try:
        result = await service.compare(experiment_id, persist=persist)
    except ExperimentNotFoundError as e:
        raise HTTPException(status_code=404, detail="experiment not found") from e
    return ComparisonRead(
        experiment_id=result.experiment_id,
        variants=[
            VariantComparisonRead(
                variant_id=c.variant_id,
                strategy_version_id=c.strategy_version_id,
                role=c.role,
                label=c.label,
                metrics=VariantMetricsRead(**c.metrics.__dict__),
            )
            for c in result.variants
        ],
        winner_variant_id=result.winner_variant_id,
    )
