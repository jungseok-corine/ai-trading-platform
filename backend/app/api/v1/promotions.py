"""paper → 실전 승격 게이트 API (C-2.30).

전략 버전이 실전 적용 후보로 승격될 수 있는지 기준을 정의하고 평가한다.
⚠️ 평가 통과는 판단일 뿐이며, 실거래를 자동으로 켜지 않는다(사람 확인 + KIS 플래그 필요).
"""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import MarketCode
from app.services.promotion_service import (
    PromotionCriteriaNotFoundError,
    PromotionService,
    StrategyVersionNotFoundError,
)

router = APIRouter(tags=["promotions"])


def get_service(session: AsyncSession = Depends(get_db)) -> PromotionService:
    return PromotionService(session)


class CriteriaCreateRequest(BaseModel):
    name: str
    market: MarketCode = MarketCode.KR
    min_trade_count: int = 50
    min_days: int = 30
    min_expectancy: Decimal = Decimal("0")
    max_drawdown: Decimal | None = None


class CriteriaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market: MarketCode
    name: str
    min_trade_count: int
    min_days: int
    min_expectancy: Decimal
    max_drawdown: Decimal | None
    enabled: bool
    created_at: datetime


class CheckRead(BaseModel):
    name: str
    passed: bool
    actual: str
    threshold: str


class EvaluationRead(BaseModel):
    strategy_version_id: int
    criteria_id: int
    passed: bool
    trades_count: int
    days: int
    expectancy: Decimal
    max_drawdown: Decimal
    checks: list[CheckRead]


@router.post("/promotion-criteria", response_model=CriteriaRead, status_code=201)
async def create_criteria(
    payload: CriteriaCreateRequest, service: PromotionService = Depends(get_service)
) -> CriteriaRead:
    criteria = await service.create_criteria(
        name=payload.name,
        market=payload.market,
        min_trade_count=payload.min_trade_count,
        min_days=payload.min_days,
        min_expectancy=payload.min_expectancy,
        max_drawdown=payload.max_drawdown,
    )
    return CriteriaRead.model_validate(criteria)


@router.get("/promotion-criteria", response_model=list[CriteriaRead])
async def list_criteria(
    market: MarketCode | None = Query(default=None),
    service: PromotionService = Depends(get_service),
) -> list[CriteriaRead]:
    items = await service.list_criteria(market=market)
    return [CriteriaRead.model_validate(c) for c in items]


@router.post(
    "/strategy-versions/{version_id}/promotion-evaluation",
    response_model=EvaluationRead,
)
async def evaluate_promotion(
    version_id: int,
    criteria_id: int = Query(...),
    persist: bool = Query(default=False),
    service: PromotionService = Depends(get_service),
) -> EvaluationRead:
    """전략 버전을 승격 기준에 대해 평가한다. 통과해도 실거래는 자동으로 켜지지 않는다."""
    try:
        result = await service.evaluate(version_id, criteria_id, persist=persist)
    except StrategyVersionNotFoundError as e:
        raise HTTPException(status_code=404, detail="strategy version not found") from e
    except PromotionCriteriaNotFoundError as e:
        raise HTTPException(status_code=404, detail="promotion criteria not found") from e
    return EvaluationRead(
        strategy_version_id=result.strategy_version_id,
        criteria_id=result.criteria_id,
        passed=result.passed,
        trades_count=result.trades_count,
        days=result.days,
        expectancy=result.expectancy,
        max_drawdown=result.max_drawdown,
        checks=[CheckRead(**c.to_dict()) for c in result.checks],
    )
