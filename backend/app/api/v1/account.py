from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_broker_client
from app.trading.broker.base import BrokerClient
from app.trading.broker.exceptions import KISAPIError
from app.trading.broker.schemas import AccountBalance

router = APIRouter(prefix="/account", tags=["account"])


@router.get("", response_model=AccountBalance)
async def get_account(
    broker: BrokerClient = Depends(get_broker_client),
) -> AccountBalance:
    try:
        return await broker.get_account_balance()
    except KISAPIError as e:
        raise HTTPException(status_code=502, detail=e.msg1) from e
