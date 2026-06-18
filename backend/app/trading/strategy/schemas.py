from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.models.enums import PauseSource, SchedulerRunStatus, StrategyVersionStatus, TradeSide


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
    signal_price: Decimal | None = None
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


class StrategyParameterMeta(BaseModel):
    """단일 파라미터의 메타데이터 (프론트 폼 생성에 사용)."""

    name: str
    type: str
    default: str | int | float | bool | None
    min: int | float | None = None
    max: int | float | None = None
    description: str
    required: bool = False


class StrategyTypeMeta(BaseModel):
    """전략 타입의 메타데이터 (GET /strategy-types 응답 항목)."""

    strategy_type: str
    display_name: str
    display_name_ko: str
    parameters: list[StrategyParameterMeta]


STRATEGY_TYPES_METADATA: list[StrategyTypeMeta] = [
    StrategyTypeMeta(
        strategy_type="moving_average_cross",
        display_name="Moving Average Cross",
        display_name_ko="이동평균 교차",
        parameters=[
            StrategyParameterMeta(name="short_window", type="int", default=5, min=1, description="단기 이동평균 기간"),
            StrategyParameterMeta(name="long_window", type="int", default=20, min=2, description="장기 이동평균 기간 (short_window 초과)"),
            StrategyParameterMeta(name="quantity", type="int", default=1, min=1, description="주문 수량"),
        ],
    ),
    StrategyTypeMeta(
        strategy_type="volume_confirmed_ma_cross",
        display_name="Volume Confirmed MA Cross",
        display_name_ko="거래량 확인 MA 교차",
        parameters=[
            StrategyParameterMeta(name="short_window", type="int", default=5, min=1, description="단기 이동평균 기간"),
            StrategyParameterMeta(name="long_window", type="int", default=20, min=2, description="장기 이동평균 기간 (short_window 초과)"),
            StrategyParameterMeta(name="volume_window", type="int", default=20, min=1, description="거래량 SMA 계산 기간"),
            StrategyParameterMeta(name="volume_multiplier", type="float", default=1.5, min=0.01, description="거래량 spike 판단 배수 (volume_sma 대비 배수)"),
            StrategyParameterMeta(name="quantity", type="int", default=1, min=1, description="주문 수량"),
        ],
    ),
]


class StrategyVersionParameters(BaseModel):
    """strategy_versions.parameters JSONB에 저장되는 구조.

    StrategyRunnerService가 그대로 읽는 공통 키 + 전략 타입별 추가 키를 포함한다.
    volume_window/volume_multiplier는 volume_confirmed_ma_cross 전용이지만,
    기존 moving_average_cross 버전의 하위호환을 위해 모두 optional with defaults.
    """

    strategy_type: str = "moving_average_cross"
    symbol_code: str
    short_window: int = Field(default=5, gt=0)
    long_window: int = Field(default=20, gt=0)
    quantity: int = Field(default=1, gt=0)
    timeframe: str = "1m"
    account_id: int | None = None
    enabled: bool = True
    auto_trade_enabled: bool = False
    # volume_confirmed_ma_cross 전용 파라미터 (moving_average_cross에서는 무시됨)
    volume_window: int = Field(default=20, gt=0)
    volume_multiplier: float = Field(default=1.5, gt=0)

    @model_validator(mode="after")
    def _validate(self) -> "StrategyVersionParameters":
        if self.long_window <= self.short_window:
            raise ValueError(
                f"long_window({self.long_window})은 short_window({self.short_window})보다 커야 합니다."
            )
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


# ---------------------------------------------------------------------------
# Trading State Sync (C-2.11)
# ---------------------------------------------------------------------------


class TradingStateSyncResultRead(BaseModel):
    account_id: int
    broker_mode: str
    started_at: datetime
    completed_at: datetime
    orders_checked: int
    orders_updated: int
    orders_cancelled: int
    order_sync_errors: list[str]
    order_sync_error_category: str | None = None
    order_sync_skipped_reason: str | None = None
    positions_compared: int
    mismatches_count: int
    risk_events_created: int
    positions_synced_to_db: bool
    position_errors: list[str]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Trading Guard (C-2.12)
# ---------------------------------------------------------------------------


class TradingGuardStateRead(BaseModel):
    account_id: int
    is_paused: bool
    pause_reason: str | None = None
    pause_source: PauseSource | None = None
    paused_at: datetime | None = None
    paused_by: str | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_note: str | None = None
    related_risk_event_id: int | None = None
    updated_at: datetime | None = None


class PauseRequest(BaseModel):
    reason: str


class ResumeRequest(BaseModel):
    resolution_note: str | None = None


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
# Signal Outcome Analysis (Phase C-0)
# ---------------------------------------------------------------------------


class SignalOutcomeHorizonResult(BaseModel):
    """특정 horizon에서의 가격 반응 결과."""

    horizon_minutes: int
    close_price: Decimal | None
    return_pct: Decimal | None  # (close - entry) / entry * 100; 항상 raw — BUY 양수=좋음, SELL 음수=좋음
    available: bool  # False = market_data 없음
    is_win: bool | None = None  # 신호 방향 기준 성공 여부; unavailable이면 None
    directional_return_pct: Decimal | None = None  # BUY: return_pct 그대로; SELL: -return_pct; 양수=신호 방향 맞음


class SignalOutcomeRead(BaseModel):
    """단일 신호의 이후 가격 반응 분석 결과."""

    signal_id: int
    symbol_code: str
    signal_type: TradeSide
    signal_ts: datetime  # candle_ts (없으면 generated_at 대체)
    timeframe: str
    entry_price: Decimal | None  # 신호 다음 캔들의 open; None이면 market_data 없음
    horizons: list[SignalOutcomeHorizonResult]
    mfe_pct: Decimal | None  # 최대 유리 변동폭 (신호 방향 기준, 양수)
    mae_pct: Decimal | None  # 최대 불리 변동폭 (신호 방향 기준, 양수)
    available: bool  # False = 신호 이후 market_data 전혀 없음
    note: str | None = None


class SignalOutcomeByHorizon(BaseModel):
    """horizon별 집계 통계."""

    horizon_minutes: int
    count: int  # 해당 horizon 데이터가 있는 신호 수
    avg_return_pct: Decimal
    win_rate: Decimal  # 신호 방향과 일치하는 비율 (BUY에서 양수, SELL에서 음수)


class SignalOutcomeBySymbol(BaseModel):
    """종목별 신호 성과 요약."""

    symbol_code: str
    signal_count: int
    analyzed_count: int
    win_rate_5m: Decimal | None  # 5분 horizon win rate; 데이터 없으면 None


class SignalOutcomeBySignalType(BaseModel):
    """신호 종류별 성과 요약."""

    signal_type: TradeSide
    signal_count: int
    analyzed_count: int
    win_rate_5m: Decimal | None


class SignalOutcomeSummary(BaseModel):
    """전체 신호 결과 요약."""

    total_signals: int
    analyzed_count: int  # market_data 있어서 분석된 신호 수
    skipped_count: int  # market_data 없거나 분석 불가 신호 수
    by_horizon: list[SignalOutcomeByHorizon]
    by_symbol: list[SignalOutcomeBySymbol]
    by_signal_type: list[SignalOutcomeBySignalType]


# ---------------------------------------------------------------------------
# Strategy Version Performance (Phase C-1)
# ---------------------------------------------------------------------------


class StrategyVersionPerformanceByHorizon(BaseModel):
    """horizon별 신호 성과 집계."""

    horizon_minutes: int
    count: int
    win_rate: Decimal
    avg_return_pct: Decimal
    avg_directional_return_pct: Decimal  # BUY/SELL 방향 조정 평균 수익률
    avg_mfe_pct: Decimal | None  # 해당 horizon 데이터 있는 신호의 평균 MFE
    avg_mae_pct: Decimal | None  # 해당 horizon 데이터 있는 신호의 평균 MAE


class StrategyVersionPerformanceBySignalType(BaseModel):
    """신호 종류(BUY/SELL)별 성과 집계."""

    signal_type: TradeSide
    signal_count: int
    analyzed_count: int
    win_rate_5m: Decimal | None
    avg_directional_return_pct_5m: Decimal | None


class StrategyVersionPerformanceBySymbol(BaseModel):
    """종목별 성과 집계."""

    symbol_code: str
    signal_count: int
    analyzed_count: int
    win_rate_5m: Decimal | None
    avg_directional_return_pct_5m: Decimal | None


class StrategyVersionActualTradingPerformance(BaseModel):
    """실제 체결 기반 성과. pnl_amount가 기록된 체결 건만 집계."""

    trade_count: int
    filled_count: int
    total_pnl_amount: Decimal | None
    win_trade_count: int | None
    loss_trade_count: int | None
    note: str


class StrategyVersionPerformanceRead(BaseModel):
    """strategy_version 단위 성과 집계 응답."""

    strategy_id: int
    strategy_version_id: int
    total_signals: int
    analyzed_signals: int
    skipped_signals: int
    by_horizon: list[StrategyVersionPerformanceByHorizon]
    by_signal_type: list[StrategyVersionPerformanceBySignalType]
    by_symbol: list[StrategyVersionPerformanceBySymbol]
    actual_trading: StrategyVersionActualTradingPerformance | None


# ---------------------------------------------------------------------------
# AI Analysis Input Payload (Phase C-2.0)
# ---------------------------------------------------------------------------


class AnalysisInputStrategyMeta(BaseModel):
    """분석 대상 strategy/version 메타데이터."""

    strategy_id: int
    strategy_name: str
    strategy_version_id: int
    version_no: int
    status: StrategyVersionStatus
    parameters: dict


class AnalysisInputMarketData(BaseModel):
    """분석 대상 종목의 market_data 요약."""

    symbols: list[str]
    timeframes: list[str]
    latest_ts: datetime | None
    row_count: int


class AnalysisInputSignalOutcome5m(BaseModel):
    """5분 horizon 결과 요약 (optional; 데이터 없으면 None)."""

    directional_return_pct: Decimal | None
    is_win: bool | None


class AnalysisInputRecentSignal(BaseModel):
    """최근 신호 및 5분 결과 (시간 경과 불충분 시 outcome_5m=None)."""

    signal_id: int
    symbol_code: str
    signal_type: TradeSide
    generated_at: datetime
    outcome_5m: AnalysisInputSignalOutcome5m | None


class AnalysisInputContext(BaseModel):
    """payload 생성 시점 및 분석 제한 사항."""

    generated_at: datetime
    limitations: list[str]
    trading_paused: bool = False
    pause_reason: str | None = None


class StrategyAnalysisInputRead(BaseModel):
    """LLM에 바로 넘길 수 있는 strategy_version 분석 입력 payload."""

    strategy: AnalysisInputStrategyMeta
    performance: StrategyVersionPerformanceRead
    market_data: AnalysisInputMarketData
    recent_signals: list[AnalysisInputRecentSignal]
    analysis_context: AnalysisInputContext


# ---------------------------------------------------------------------------
# Analysis Prompt (Phase C-2.1)
# ---------------------------------------------------------------------------


class AnalysisPromptInputSummary(BaseModel):
    """prompt 생성에 사용된 데이터 요약 — 응답에 포함해 디버깅/로깅을 돕는다."""

    total_signals: int
    analyzed_signals: int
    symbols: list[str]
    timeframes: list[str]
    max_prompt_length: int
    included_recent_signals_count: int
    included_symbols_count: int


class StrategyAnalysisPromptRead(BaseModel):
    """LLM 분석용 prompt preview 응답."""

    strategy_id: int
    strategy_version_id: int
    prompt_type: str
    prompt: str
    prompt_length: int
    truncated: bool
    input_summary: AnalysisPromptInputSummary
    warnings: list[str]


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
