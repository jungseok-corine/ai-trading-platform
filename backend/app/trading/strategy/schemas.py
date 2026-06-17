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
    last_error_category: str | None = None
    active_strategy_count: int
    order_sync_last_run_at: datetime | None
    order_sync_last_error: str | None
    order_sync_last_error_category: str | None = None
    recent_run_has_failure: bool
    auto_trade_enabled_count: int


class OrderSyncExecutionSummary(BaseModel):
    order_id: str
    filled_quantity: int
    filled_price: float | None = None


class OrderSyncResultRead(BaseModel):
    checked: int
    updated: int
    matched: int
    unmatched: int
    unmatched_order_ids: list[str]
    executions: list[OrderSyncExecutionSummary] = []
    errors: list[str]
    error_category: str | None = None
    skipped_reason: str | None = None


class SignalLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol_code: str
    symbol_name: str | None = None
    symbol_display: str | None = None
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


class SchedulerSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_scheduler_interval_seconds: int
    order_sync_scheduler_interval_seconds: int
    updated_at: datetime


class SchedulerSettingsUpdateRequest(BaseModel):
    strategy_scheduler_interval_seconds: int | None = None
    order_sync_scheduler_interval_seconds: int | None = None


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


class WatchlistCreateRequest(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True


class WatchlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    enabled: bool
    symbol_count: int = 0
    created_at: datetime
    updated_at: datetime


class WatchlistSymbolCreateRequest(BaseModel):
    symbol_code: str
    symbol_name: str | None = None
    enabled: bool = True
    note: str | None = None


class WatchlistSymbolUpdateRequest(BaseModel):
    symbol_name: str | None = None
    enabled: bool | None = None
    note: str | None = None


class WatchlistSymbolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    watchlist_id: int
    symbol_code: str
    symbol_name: str | None
    enabled: bool
    note: str | None
    created_at: datetime
    updated_at: datetime


class WatchlistBulkStrategyCreateRequest(BaseModel):
    """Watchlist에 등록된 활성 종목들에 대해 strategy_version을 일괄 생성하기 위한 요청.

    안전장치: bulk 생성에서는 auto_trade_enabled=true를 허용하지 않는다.
    자동매매는 생성 후 개별 전략 버전 화면에서 하나씩 켜야 한다.
    """

    strategy_id: int
    short_window: int = 5
    long_window: int = 20
    timeframe: str = "5m"
    quantity: int = 1
    account_id: int | None = None
    status: StrategyVersionStatus = StrategyVersionStatus.TESTING
    auto_trade_enabled: bool = False

    @model_validator(mode="after")
    def _validate_auto_trade_disabled(self) -> "WatchlistBulkStrategyCreateRequest":
        if self.auto_trade_enabled:
            raise ValueError("Watchlist 기반 bulk 생성에서는 auto_trade_enabled=true를 허용하지 않습니다.")
        return self


class WatchlistBulkStrategyCreateItem(BaseModel):
    symbol_code: str
    symbol_name: str | None
    created: bool
    strategy_version_id: int | None
    reason: str | None


class WatchlistBulkStrategyCreateResponse(BaseModel):
    strategy_id: int
    items: list[WatchlistBulkStrategyCreateItem]


# ---------------------------------------------------------------------------
# Market Data
# ---------------------------------------------------------------------------


class MarketDataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol_code: str
    timeframe: str
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class MarketDataTimeframeSummary(BaseModel):
    timeframe: str
    count: int
    oldest_ts: datetime | None
    latest_ts: datetime | None


class MarketDataSymbolSummary(BaseModel):
    symbol_code: str
    total_count: int
    oldest_ts: datetime | None
    latest_ts: datetime | None
    by_timeframe: list[MarketDataTimeframeSummary]


class MarketDataSymbolOverview(BaseModel):
    symbol_code: str
    total_count: int
    latest_ts: datetime | None
    timeframes: list[str]


class MarketDataGlobalSummary(BaseModel):
    total_symbols: int
    total_rows: int
    symbols: list[MarketDataSymbolOverview]
