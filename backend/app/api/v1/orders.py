from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client, get_overseas_broker_client
from app.db.session import get_db
from app.services.risk_service import RiskConfigNotFoundError, RiskService
from app.services.trade_service import TradeService
from app.trading.broker.base import BrokerClient
from app.trading.broker.exceptions import KISAPIError
from app.trading.order.schemas import OrderCreateRequest, OrderResponse, TradeRead

router = APIRouter(tags=["orders"])


def get_trade_service(
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
    overseas_broker: BrokerClient | None = Depends(get_overseas_broker_client),
) -> TradeService:
    risk_service = RiskService(session, broker)
    return TradeService(session, broker, risk_service, overseas_broker=overseas_broker)


@router.post("/orders", response_model=OrderResponse)
async def create_order(
    payload: OrderCreateRequest,
    service: TradeService = Depends(get_trade_service),
) -> OrderResponse:
    try:
        result = await service.place_order(payload)
    except RiskConfigNotFoundError as e:
        raise HTTPException(status_code=404, detail="risk config not found") from e
    except KISAPIError as e:
        raise HTTPException(status_code=502, detail=e.msg1) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return OrderResponse(
        approved=result.approved,
        rule_name=result.rule_name,
        reason=result.reason,
        trade=TradeRead.model_validate(result.trade) if result.trade else None,
    )


@router.get("/trades", response_model=list[TradeRead])
async def list_trades(
    account_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    service: TradeService = Depends(get_trade_service),
) -> list[TradeRead]:
    return await service.list_trades(account_id=account_id, limit=limit, offset=offset)


@router.get("/trades/{trade_id}", response_model=TradeRead)
async def get_trade(
    trade_id: int,
    service: TradeService = Depends(get_trade_service),
) -> TradeRead:
    trade = await service.get_trade(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="trade not found")
    return trade
