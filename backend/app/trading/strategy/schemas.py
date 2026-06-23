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
    market: str = "KR"
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


class StrategyUpdateRequest(BaseModel):
    name: str | None = None
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
    StrategyTypeMeta(
        strategy_type="flow_confirmed_volume_ma_cross",
        display_name="Flow Confirmed Volume MA Cross",
        display_name_ko="수급 확인 거래량 MA 교차",
        parameters=[
            StrategyParameterMeta(name="short_window", type="int", default=5, min=1, description="단기 이동평균 기간"),
            StrategyParameterMeta(name="long_window", type="int", default=20, min=2, description="장기 이동평균 기간 (short_window 초과)"),
            StrategyParameterMeta(name="volume_window", type="int", default=20, min=1, description="거래량 SMA 계산 기간"),
            StrategyParameterMeta(name="volume_multiplier", type="float", default=1.5, min=0.01, description="거래량 spike 판단 배수"),
            StrategyParameterMeta(name="quantity", type="int", default=1, min=1, description="주문 수량"),
            StrategyParameterMeta(name="flow_lookback_days", type="int", default=5, min=1, description="수급 데이터 조회 기간 (일)"),
            StrategyParameterMeta(name="max_flow_age_days", type="int", default=5, min=1, description="수급 데이터 최대 허용 경과일 (초과 시 stale 처리)"),
            StrategyParameterMeta(
                name="flow_mode",
                type="str",
                default="foreign_or_institution",
                description="수급 필터 모드: foreign_or_institution / foreign_and_institution / smart_money_vs_retail",
            ),
            StrategyParameterMeta(name="require_flow_data", type="bool", default=True, description="수급 데이터 없을 때 BUY 차단 여부. false면 수급 없이도 volume+MA 조건만으로 BUY 허용"),
        ],
    ),
    StrategyTypeMeta(
        strategy_type="rsi_reversion",
        display_name="RSI Reversion",
        display_name_ko="RSI 평균회귀",
        parameters=[
            StrategyParameterMeta(name="rsi_period", type="int", default=14, min=2, description="RSI 계산 기간"),
            StrategyParameterMeta(name="oversold", type="float", default=30.0, min=0.0, description="과매도 기준 (BUY: 아래→위 탈출)"),
            StrategyParameterMeta(name="overbought", type="float", default=70.0, min=0.0, description="과매수 기준 (exit_mode=overbought SELL)"),
            StrategyParameterMeta(name="exit_mode", type="str", default="overbought", description="청산 모드: overbought(과열 시) / midline(50 회귀 시)"),
            StrategyParameterMeta(name="quantity", type="int", default=1, min=1, description="주문 수량"),
        ],
    ),
    StrategyTypeMeta(
        strategy_type="macd_trend",
        display_name="MACD Trend",
        display_name_ko="MACD 추세추종",
        parameters=[
            StrategyParameterMeta(name="fast_period", type="int", default=12, min=1, description="단기 EMA 기간"),
            StrategyParameterMeta(name="slow_period", type="int", default=26, min=2, description="장기 EMA 기간 (fast 초과)"),
            StrategyParameterMeta(name="signal_period", type="int", default=9, min=1, description="시그널선 EMA 기간"),
            StrategyParameterMeta(name="require_above_zero", type="bool", default=False, description="MACD>0(0선 위)일 때만 BUY 허용"),
            StrategyParameterMeta(name="quantity", type="int", default=1, min=1, description="주문 수량"),
        ],
    ),
    StrategyTypeMeta(
        strategy_type="breakout_high",
        display_name="Breakout High",
        display_name_ko="전고점 돌파",
        parameters=[
            StrategyParameterMeta(name="breakout_lookback", type="int", default=20, min=1, description="돌파 비교 구간 (직전 N봉 최고가)"),
            StrategyParameterMeta(name="exit_lookback", type="int", default=10, min=1, description="이탈 비교 구간 (직전 N봉 최저가)"),
            StrategyParameterMeta(name="volume_confirm", type="bool", default=False, description="거래량 확인 사용 여부"),
            StrategyParameterMeta(name="volume_window", type="int", default=20, min=1, description="거래량 SMA 기간 (volume_confirm 시)"),
            StrategyParameterMeta(name="volume_multiplier", type="float", default=1.5, min=0.01, description="거래량 spike 배수 (volume_confirm 시)"),
            StrategyParameterMeta(name="quantity", type="int", default=1, min=1, description="주문 수량"),
        ],
    ),
    StrategyTypeMeta(
        strategy_type="pullback_trend",
        display_name="Pullback Trend",
        display_name_ko="눌림목 매수",
        parameters=[
            StrategyParameterMeta(name="short_window", type="int", default=10, min=1, description="단기 이동평균 기간 (눌림 후 재탈환 기준)"),
            StrategyParameterMeta(name="long_window", type="int", default=50, min=2, description="장기 이동평균 기간 (추세 기준, short 초과)"),
            StrategyParameterMeta(name="quantity", type="int", default=1, min=1, description="주문 수량"),
        ],
    ),
    StrategyTypeMeta(
        strategy_type="momentum_surge",
        display_name="Momentum Surge",
        display_name_ko="급등 모멘텀",
        parameters=[
            StrategyParameterMeta(name="surge_lookback", type="int", default=5, min=1, description="모멘텀 측정 구간 (직전 N봉 수익률)"),
            StrategyParameterMeta(name="surge_threshold_pct", type="float", default=5.0, min=0.01, description="급등 진입 기준 수익률(%) — 클수록 더 강한 급등만"),
            StrategyParameterMeta(name="exit_drop_pct", type="float", default=3.0, min=0.01, description="모멘텀 소멸 청산 기준 하락률(%)"),
            StrategyParameterMeta(name="volume_window", type="int", default=20, min=1, description="거래량 SMA 기간"),
            StrategyParameterMeta(name="volume_multiplier", type="float", default=2.0, min=0.01, description="거래량 급증 확인 배수 (volume_sma 대비)"),
            StrategyParameterMeta(name="quantity", type="int", default=1, min=1, description="주문 수량"),
        ],
    ),
]


_VALID_FLOW_MODES = frozenset(
    {"foreign_or_institution", "foreign_and_institution", "smart_money_vs_retail"}
)

# short_window/long_window 제약(long>short)이 적용되는 MA 계열 전략 타입.
_MA_WINDOW_STRATEGY_TYPES = frozenset(
    {
        "moving_average_cross",
        "volume_confirmed_ma_cross",
        "flow_confirmed_volume_ma_cross",
        "pullback_trend",
    }
)

_VALID_EXIT_MODES = frozenset({"overbought", "midline"})

# 유니버스 신호 스캔에서 허용되는 universe 이름 (UniverseResolver와 동일하게 유지).
_VALID_UNIVERSES = frozenset({"scanner_candidates", "watchlist"})

# 멀티마켓: 시장 구분 + 미국 거래소 코드(EXCD).
_VALID_MARKETS = frozenset({"KR", "US"})
_VALID_QUANTITY_MODES = frozenset({"fixed", "cash_amount", "cash_pct"})
_VALID_US_EXCHANGES = frozenset({"NAS", "NYS", "AMS"})


class StrategyVersionParameters(BaseModel):
    """strategy_versions.parameters JSONB에 저장되는 구조.

    StrategyRunnerService가 그대로 읽는 공통 키 + 전략 타입별 추가 키를 포함한다.
    하위호환을 위해 전략별 전용 파라미터도 optional with defaults로 선언한다.
    """

    strategy_type: str = "moving_average_cross"
    # universe 모드에서는 symbol_code 없이도 유효하다(유니버스가 종목을 공급).
    symbol_code: str = ""
    # 유니버스 신호 스캔: 설정 시 단일 symbol_code 대신 유니버스 전체에 전략을 돌린다.
    # (scanner_candidates / watchlist). read-only 신호 생성 전용 — auto_trade와 양립 불가.
    universe: str | None = None
    # 유니버스를 특정 시장(KR/US)으로 제한한다. None이면 전체 시장 종목을 본다.
    universe_market: str | None = None
    # 유니버스 자동매매(명시 옵트인). 모의계좌 전용 + 회당 주문 상한으로 가드된다.
    universe_auto_trade: bool = False
    max_orders_per_run: int = Field(default=5, gt=0)
    universe_lookback_days: int = Field(default=5, gt=0)
    # 멀티마켓: market=US이면 KIS 해외 분봉(exchange=EXCD)으로 시세를 조회한다. 기본 KR(국내).
    market: str = "KR"
    exchange: str = "NAS"
    short_window: int = Field(default=5, gt=0)
    long_window: int = Field(default=20, gt=0)
    quantity: int = Field(default=1, gt=0)
    # 포지션 사이징: fixed(고정 수량) / cash_amount(1회 투입 금액) / cash_pct(가용현금 %).
    quantity_mode: str = "fixed"
    cash_amount: float = Field(default=0.0, ge=0)
    cash_pct: float = Field(default=0.0, ge=0, le=100)
    timeframe: str = "1m"
    account_id: int | None = None
    enabled: bool = True
    auto_trade_enabled: bool = False
    # Phase B: 장 마감 동시호가 단계에서 당일 포지션을 '종가 청산' 매도로 정리한다(인트라데이).
    exit_on_close: bool = False
    # volume_confirmed_ma_cross 전용 파라미터
    volume_window: int = Field(default=20, gt=0)
    volume_multiplier: float = Field(default=1.5, gt=0)
    # flow_confirmed_volume_ma_cross 전용 파라미터
    flow_lookback_days: int = Field(default=5, gt=0)
    max_flow_age_days: int = Field(default=5, gt=0)
    flow_mode: str = "foreign_or_institution"
    require_flow_data: bool = True
    # rsi_reversion 전용 파라미터
    rsi_period: int = Field(default=14, gt=0)
    oversold: float = Field(default=30.0, ge=0)
    overbought: float = Field(default=70.0, ge=0)
    exit_mode: str = "overbought"
    # macd_trend 전용 파라미터
    fast_period: int = Field(default=12, gt=0)
    slow_period: int = Field(default=26, gt=0)
    signal_period: int = Field(default=9, gt=0)
    require_above_zero: bool = False
    # breakout_high 전용 파라미터
    breakout_lookback: int = Field(default=20, gt=0)
    exit_lookback: int = Field(default=10, gt=0)
    volume_confirm: bool = False
    # momentum_surge 전용 파라미터
    surge_lookback: int = Field(default=5, gt=0)
    surge_threshold_pct: float = Field(default=5.0, gt=0)
    exit_drop_pct: float = Field(default=3.0, gt=0)

    @model_validator(mode="after")
    def _validate(self) -> "StrategyVersionParameters":
        # short/long_window는 MA 계열 전략에서만 의미가 있으므로 해당 타입에만 적용한다.
        if self.strategy_type in _MA_WINDOW_STRATEGY_TYPES and self.long_window <= self.short_window:
            raise ValueError(
                f"long_window({self.long_window})은 short_window({self.short_window})보다 커야 합니다."
            )
        if self.market not in _VALID_MARKETS:
            raise ValueError(
                f"market={self.market!r}은 유효하지 않습니다. 허용값: {sorted(_VALID_MARKETS)}"
            )
        if self.market == "US" and self.exchange not in _VALID_US_EXCHANGES:
            raise ValueError(
                f"미국 시장 exchange={self.exchange!r}은 유효하지 않습니다. "
                f"허용값: {sorted(_VALID_US_EXCHANGES)}"
            )
        if self.universe is not None:
            if self.universe not in _VALID_UNIVERSES:
                raise ValueError(
                    f"universe={self.universe!r}은 유효하지 않습니다. 허용값: {sorted(_VALID_UNIVERSES)}"
                )
            # 단일종목용 auto_trade_enabled는 유니버스에서 쓰지 않는다(universe_auto_trade 사용).
            if self.auto_trade_enabled:
                raise ValueError(
                    "universe 모드에서는 auto_trade_enabled(단일종목용) 대신 "
                    "universe_auto_trade를 사용하세요."
                )
            # 유니버스 자동매매는 명시 옵트인 + account_id 필요(모의계좌 가드는 런타임에서).
            if self.universe_auto_trade and self.account_id is None:
                raise ValueError("universe_auto_trade=true 이려면 account_id가 필요합니다.")
            if self.universe_market is not None and self.universe_market not in _VALID_MARKETS:
                raise ValueError(
                    f"universe_market={self.universe_market!r}은 유효하지 않습니다. "
                    f"허용값: {sorted(_VALID_MARKETS)}"
                )
        else:
            if not self.symbol_code:
                raise ValueError("universe가 없으면 symbol_code가 필요합니다.")
            if self.universe_auto_trade:
                raise ValueError("universe_auto_trade는 universe 모드에서만 사용합니다.")
        if self.auto_trade_enabled and self.account_id is None:
            raise ValueError("auto_trade_enabled=true 이려면 account_id가 필요합니다.")
        if self.quantity_mode not in _VALID_QUANTITY_MODES:
            raise ValueError(
                f"quantity_mode={self.quantity_mode!r}은 유효하지 않습니다. "
                f"허용값: {sorted(_VALID_QUANTITY_MODES)}"
            )
        if self.quantity_mode == "cash_amount" and self.cash_amount <= 0:
            raise ValueError("quantity_mode=cash_amount 이려면 cash_amount > 0 이어야 합니다.")
        if self.quantity_mode == "cash_pct" and not (0 < self.cash_pct <= 100):
            raise ValueError("quantity_mode=cash_pct 이려면 cash_pct가 0 초과 100 이하여야 합니다.")
        if self.flow_mode not in _VALID_FLOW_MODES:
            raise ValueError(
                f"flow_mode={self.flow_mode!r}은 유효하지 않습니다. "
                f"허용값: {sorted(_VALID_FLOW_MODES)}"
            )
        if self.strategy_type == "rsi_reversion":
            if self.exit_mode not in _VALID_EXIT_MODES:
                raise ValueError(
                    f"exit_mode={self.exit_mode!r}은 유효하지 않습니다. "
                    f"허용값: {sorted(_VALID_EXIT_MODES)}"
                )
            if self.overbought <= self.oversold:
                raise ValueError(
                    f"overbought({self.overbought})는 oversold({self.oversold})보다 커야 합니다."
                )
        if self.strategy_type == "macd_trend" and self.slow_period <= self.fast_period:
            raise ValueError(
                f"slow_period({self.slow_period})는 fast_period({self.fast_period})보다 커야 합니다."
            )
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


_VALID_WATCHLIST_MARKETS = frozenset({"KR", "US"})
_VALID_WATCHLIST_US_EXCHANGES = frozenset({"NAS", "NYS", "AMS"})


def _validate_market_exchange(market: str, exchange: str | None) -> None:
    if market not in _VALID_WATCHLIST_MARKETS:
        raise ValueError(f"market은 {sorted(_VALID_WATCHLIST_MARKETS)} 중 하나여야 합니다: {market!r}")
    if market == "US":
        if exchange not in _VALID_WATCHLIST_US_EXCHANGES:
            raise ValueError(
                f"US 종목은 exchange가 {sorted(_VALID_WATCHLIST_US_EXCHANGES)} 중 하나여야 합니다: {exchange!r}"
            )


class WatchlistSymbolCreateRequest(BaseModel):
    symbol_code: str
    symbol_name: str | None = None
    market: str = "KR"
    exchange: str | None = None
    enabled: bool = True
    note: str | None = None

    @model_validator(mode="after")
    def _check_market(self) -> "WatchlistSymbolCreateRequest":
        _validate_market_exchange(self.market, self.exchange)
        return self


class WatchlistSymbolUpdateRequest(BaseModel):
    symbol_name: str | None = None
    market: str | None = None
    exchange: str | None = None
    enabled: bool | None = None
    note: str | None = None


class WatchlistSymbolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    watchlist_id: int
    symbol_code: str
    symbol_name: str | None
    market: str = "KR"
    exchange: str | None = None
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
