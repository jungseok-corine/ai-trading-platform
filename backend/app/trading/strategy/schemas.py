from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator

from app.domain.models.enums import SchedulerRunStatus, StrategyVersionStatus, TradeSide


class SignalGenerateRequest(BaseModel):
    symbol_code: str
    strategy_version_id: int | None = None


class StrategyRunResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_version_id: int | None
    symbol_code: str
    signal_created: bool
    signal_id: int | None
    auto_trade_enabled: bool
    trade_attempted: bool
    trade_approved: bool | None = None
    trade_id: int | None = None
    rejection_reason: str | None = None
    error: str | None = None
    error_category: str | None = None


class EngineStatusResponse(BaseModel):
    scheduler_running: bool
    registered_jobs: list[str]
    last_run_at: datetime | None
    last_error: str | None
    active_strategy_count: int
    order_sync_last_run_at: datetime | None
    order_sync_last_error: str | None
    recent_run_has_failure: bool
    auto_trade_enabled_count: int


class OrderSyncResultRead(BaseModel):
    checked: int
    updated: int
    matched: int
    unmatched: int
    unmatched_order_ids: list[str]
    errors: list[str]
    error_category: str | None = None
    skipped_reason: str | None = None


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


class StrategyCreateRequest(BaseModel):
    name: str
    description: str | None = None


class StrategyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime
    version_count: int = 0


class StrategyVersionParameters(BaseModel):
    """strategy_versions.parameters JSONB에 저장되는 구조.

    StrategyRunnerService가 그대로 읽는 키(strategy_type, symbol_code, short_window,
    long_window, quantity, account_id, enabled, auto_trade_enabled)와 일치한다.
    """

    strategy_type: str = "moving_average_cross"
    symbol_code: str
    short_window: int = 5
    long_window: int = 20
    quantity: int = 1
    timeframe: str = "1m"
    account_id: int | None = None
    enabled: bool = True
    auto_trade_enabled: bool = False

    @model_validator(mode="after")
    def _validate_auto_trade_requires_account(self) -> "StrategyVersionParameters":
        if self.auto_trade_enabled and self.account_id is None:
            raise ValueError("auto_trade_enabled=true 이려면 account_id가 필요합니다.")
        return self


class StrategyVersionCreateRequest(BaseModel):
    parameters: StrategyVersionParameters
    change_description: str | None = None
    status: StrategyVersionStatus = StrategyVersionStatus.DRAFT


class StrategyVersionUpdateRequest(BaseModel):
    parameters: StrategyVersionParameters | None = None
    change_description: str | None = None
    status: StrategyVersionStatus | None = None


class StrategyVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    version_no: int
    parameters: dict
    change_description: str | None
    status: StrategyVersionStatus
    win_rate: Decimal | None
    avg_profit: Decimal | None
    avg_loss: Decimal | None
    mdd: Decimal | None
    created_at: datetime
    updated_at: datetime


class SchedulerRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    status: SchedulerRunStatus
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error_message: str | None
    summary: dict | None
    created_at: datetime
