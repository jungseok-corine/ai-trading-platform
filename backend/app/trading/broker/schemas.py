import enum
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.domain.models.enums import OrderStatus, TradeSide


class PriceQuote(BaseModel):
    symbol_code: str
    current_price: Decimal
    change: Decimal
    change_rate: Decimal
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    volume: int


class MinuteCandle(BaseModel):
    business_date: str
    trade_time: str
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int


class AccountHolding(BaseModel):
    symbol_code: str
    symbol_name: str
    quantity: int
    avg_purchase_price: Decimal
    current_price: Decimal
    evaluation_amount: Decimal
    profit_loss_amount: Decimal
    profit_loss_rate: Decimal


class AccountSummary(BaseModel):
    total_deposit: Decimal
    total_purchase_amount: Decimal
    total_evaluation_amount: Decimal
    total_profit_loss_amount: Decimal


class AccountBalance(BaseModel):
    holdings: list[AccountHolding]
    summary: AccountSummary


class OrderType(str, enum.Enum):
    LIMIT = "limit"
    MARKET = "market"


class OrderRequest(BaseModel):
    symbol_code: str
    side: TradeSide
    quantity: int
    price: Decimal
    order_type: OrderType = OrderType.LIMIT


class OrderResult(BaseModel):
    broker_order_id: str
    order_status: OrderStatus
    ordered_at: datetime


class OrderExecution(BaseModel):
    """KIS 주문체결조회 응답 1건을 정규화한 모델."""

    broker_order_id: str
    total_quantity: int
    filled_quantity: int
    filled_price: Decimal | None = None
    cancelled: bool = False
    recorded_at: datetime | None = None
    raw: dict
