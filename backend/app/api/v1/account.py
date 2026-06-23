from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client
from app.db.session import get_db
from app.domain.repositories.account import AccountRepository
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


class AccountRead(BaseModel):
    id: int
    account_type: str  # paper / live
    broker_account_no: str
    alias: str | None = None


@router.get("/list", response_model=list[AccountRead])
async def list_accounts(session: AsyncSession = Depends(get_db)) -> list[AccountRead]:
    """등록된 계좌 목록(드롭다운 선택용). 자동매매 account_id 선택에 쓴다."""
    accounts = await AccountRepository(session).list_all()
    return [
        AccountRead(
            id=a.id, account_type=a.account_type.value,
            broker_account_no=a.broker_account_no, alias=a.alias,
        )
        for a in accounts
    ]
