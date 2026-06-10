from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.models.enums import TradeSide


class SignalGenerateRequest(BaseModel):
    symbol_code: str
    strategy_version_id: int | None = None


class EngineStatusResponse(BaseModel):
    scheduler_running: bool
    registered_jobs: list[str]
    last_run_at: datetime | None
    last_error: str | None
    active_strategy_count: int


class SignalLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol_code: str
    strategy_version_id: int | None
    signal_type: TradeSide
    generated_at: datetime
    candle_ts: datetime | None
    reason: str | None
    short_ma: Decimal | None
    long_ma: Decimal | None
    price: Decimal | None
    quantity: int | None
    created_at: datetime
