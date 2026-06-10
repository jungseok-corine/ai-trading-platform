from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class RiskConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    max_daily_loss_amount: Decimal
    max_position_size: Decimal
    max_open_positions: int
    max_trades_per_day: int
    consecutive_loss_limit: int
    emergency_stop: bool
    updated_at: datetime


class RiskConfigUpdate(BaseModel):
    max_daily_loss_amount: Decimal | None = None
    max_position_size: Decimal | None = None
    max_open_positions: int | None = None
    max_trades_per_day: int | None = None
    consecutive_loss_limit: int | None = None
    emergency_stop: bool | None = None


class EmergencyStopRequest(BaseModel):
    enabled: bool
