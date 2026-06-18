from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.models.enums import PositionEventType
from app.services.position_reconciliation_service import (
    ReconciliationMismatch,
    ReconciliationMismatchType,
    ReconciliationResult,
)


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


class ReconciliationMismatchRead(BaseModel):
    mismatch_type: ReconciliationMismatchType
    symbol_code: str
    symbol_name: str | None
    db_quantity: int | None
    broker_quantity: int | None
    db_avg_price: Decimal | None
    broker_avg_price: Decimal | None
    details: str

    @classmethod
    def from_mismatch(cls, m: ReconciliationMismatch) -> "ReconciliationMismatchRead":
        return cls(
            mismatch_type=m.mismatch_type,
            symbol_code=m.symbol_code,
            symbol_name=m.symbol_name,
            db_quantity=m.db_quantity,
            broker_quantity=m.broker_quantity,
            db_avg_price=m.db_avg_price,
            broker_avg_price=m.broker_avg_price,
            details=m.details,
        )


class ReconciliationResultRead(BaseModel):
    account_id: int
    broker_position_count: int
    db_position_count: int
    mismatch_count: int
    comparisons: list[ReconciliationMismatchRead]
    synced_to_db: bool
    risk_event_created: bool
    auto_paused: bool = False

    @classmethod
    def from_result(cls, r: ReconciliationResult) -> "ReconciliationResultRead":
        return cls(
            account_id=r.account_id,
            broker_position_count=r.broker_position_count,
            db_position_count=r.db_position_count,
            mismatch_count=r.mismatch_count,
            comparisons=[ReconciliationMismatchRead.from_mismatch(c) for c in r.comparisons],
            synced_to_db=r.synced_to_db,
            risk_event_created=r.risk_event_created,
            auto_paused=r.auto_paused,
        )


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
