from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client
from app.db.session import get_db
from app.domain.models.enums import TradeSide
from app.services.market_data_service import MarketDataService
from app.services.signal_outcome_service import SignalOutcomeService
from app.services.signal_service import SignalService
from app.trading.broker.base import BrokerClient
from app.trading.broker.exceptions import KISAPIError
from app.trading.strategy.moving_average_cross import MovingAverageCrossStrategy
from app.trading.strategy.schemas import (
    SignalGenerateRequest,
    SignalLogRead,
    SignalOutcomeRead,
    SignalOutcomeSummary,
)

router = APIRouter(prefix="/signals", tags=["signals"])


def get_signal_service(
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
) -> SignalService:
    return SignalService(session, MarketDataService(broker, session))


def get_outcome_service(session: AsyncSession = Depends(get_db)) -> SignalOutcomeService:
    return SignalOutcomeService(session)


@router.post("/generate", response_model=SignalLogRead | None)
async def generate_signal(
    payload: SignalGenerateRequest,
    service: SignalService = Depends(get_signal_service),
) -> SignalLogRead | None:
    try:
        log = await service.generate_and_log_signal(
            MovingAverageCrossStrategy(), payload.symbol_code, payload.strategy_version_id
        )
    except KISAPIError as e:
        raise HTTPException(status_code=502, detail=e.msg1) from e

    if log is None:
        return None
    return await service.get_signal(log.id)


# NOTE: /outcomes/summary 는 /{signal_id} 패턴에 가로채이지 않도록 먼저 정의한다.
@router.get("/outcomes/summary", response_model=SignalOutcomeSummary)
async def get_outcomes_summary(
    limit: int = Query(default=100, ge=1, le=500),
    signal_type: TradeSide | None = Query(default=None),
    symbol_code: str | None = Query(default=None),
    service: SignalOutcomeService = Depends(get_outcome_service),
) -> SignalOutcomeSummary:
    """최근 신호들의 이후 가격 반응을 집계한 요약을 반환한다.

    analyzed_count: market_data가 있어 분석된 신호 수
    skipped_count: market_data가 없어 건너뛴 신호 수
    by_horizon: 5/15/30/60분별 평균 수익률 및 win rate (신호 방향 기준)
    """
    return await service.get_summary(
        limit=limit,
        signal_type=signal_type,
        symbol_code=symbol_code,
    )


@router.get("", response_model=list[SignalLogRead])
async def list_signals(
    limit: int = 100,
    offset: int = 0,
    service: SignalService = Depends(get_signal_service),
) -> list[SignalLogRead]:
    return await service.list_signals(limit, offset)


@router.get("/{signal_id}/outcome", response_model=SignalOutcomeRead)
async def get_signal_outcome(
    signal_id: int,
    service: SignalOutcomeService = Depends(get_outcome_service),
) -> SignalOutcomeRead:
    """신호 발생 이후 5/15/30/60분 가격 반응을 반환한다.

    market_data가 없으면 available=False로 반환한다 (404가 아님).
    신호 자체가 없으면 404.
    """
    outcome = await service.get_outcome(signal_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="signal not found")
    return outcome


@router.get("/{signal_id}", response_model=SignalLogRead)
async def get_signal(
    signal_id: int,
    service: SignalService = Depends(get_signal_service),
) -> SignalLogRead:
    log = await service.get_signal(signal_id)
    if log is None:
        raise HTTPException(status_code=404, detail="signal not found")
    return log
