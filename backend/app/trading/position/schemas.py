from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.models.enums import PositionEventType


class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    symbol_code: str
    symbol_name: str | None
    quantity: int
    avg_entry_price: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    last_price: Decimal | None
    updated_at: datetime


class RefreshPricesResultRead(BaseModel):
    updated: int
    positions: list[PositionRead]


class BrokerSyncResultRead(BaseModel):
    created: int
    updated: int
    zeroed: int
    positions: list[PositionRead]


class PortfolioSummaryRead(BaseModel):
    account_id: int
    position_count: int
    total_quantity: int
    total_cost_amount: Decimal
    total_eval_amount: Decimal
    total_unrealized_pnl: Decimal
    total_unrealized_pnl_pct: Decimal
    total_realized_pnl: Decimal
    total_pnl: Decimal


class PositionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position_id: int
    trade_id: int | None
    event_type: PositionEventType
    quantity_delta: int
    price: Decimal | None
    realized_pnl_delta: Decimal | None
    before_quantity: int
    after_quantity: int
    before_avg_entry_price: Decimal | None
    after_avg_entry_price: Decimal | None
    raw: dict | None
    created_at: datetime
