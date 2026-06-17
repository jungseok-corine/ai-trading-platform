from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client
from app.db.session import get_db
from app.services.market_data_service import MarketDataService
from app.services.signal_service import SignalService
from app.trading.broker.base import BrokerClient
from app.trading.broker.exceptions import KISAPIError
from app.trading.strategy.moving_average_cross import MovingAverageCrossStrategy
from app.trading.strategy.schemas import SignalGenerateRequest, SignalLogRead

router = APIRouter(prefix="/signals", tags=["signals"])


def get_signal_service(
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
) -> SignalService:
    return SignalService(session, MarketDataService(broker))


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


@router.get("", response_model=list[SignalLogRead])
async def list_signals(
    limit: int = 100,
    offset: int = 0,
    service: SignalService = Depends(get_signal_service),
) -> list[SignalLogRead]:
    return await service.list_signals(limit, offset)


@router.get("/{signal_id}", response_model=SignalLogRead)
async def get_signal(
    signal_id: int,
    service: SignalService = Depends(get_signal_service),
) -> SignalLogRead:
    log = await service.get_signal(signal_id)
    if log is None:
        raise HTTPException(status_code=404, detail="signal not found")
    return log
