from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.models.enums import OrderStatus, TradeSide
from app.trading.broker.schemas import OrderType


class OrderCreateRequest(BaseModel):
    account_id: int
    symbol_code: str
    side: TradeSide
    quantity: int
    price: Decimal
    order_type: OrderType = OrderType.LIMIT
    strategy_version_id: int | None = None
    reason: str | None = None


class TradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    strategy_version_id: int | None
    symbol_code: str
    symbol_name: str | None
    side: TradeSide
    entry_time: datetime | None
    exit_time: datetime | None
    entry_price: Decimal | None
    exit_price: Decimal | None
    quantity: int
    pnl_amount: Decimal | None
    pnl_pct: Decimal | None
    entry_reason: str | None
    exit_reason: str | None
    market_condition: dict | None
    ai_analysis_id: int | None
    order_status: OrderStatus
    broker_order_id: str | None
    partial_fill: dict | None
    position_applied_quantity: int
    commission: Decimal | None
    tax: Decimal | None
    slippage: Decimal | None
    created_at: datetime


class OrderResponse(BaseModel):
    approved: bool
    rule_name: str | None = None
    reason: str | None = None
    trade: TradeRead | None = None
