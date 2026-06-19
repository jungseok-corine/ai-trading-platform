import enum


class AccountType(str, enum.Enum):
    PAPER = "paper"
    LIVE = "live"


class MarketCode(str, enum.Enum):
    """거래 시장 구분. 멀티마켓(한국장/미국장) 확장을 위해 모든 신규 엔티티에 포함한다."""

    KR = "KR"
    US = "US"


class StrategyVersionStatus(str, enum.Enum):
    DRAFT = "draft"
    TESTING = "testing"
    ACTIVE = "active"
    RETIRED = "retired"
    ARCHIVED = "archived"


class TradeSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class RiskEventResult(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class PositionEventType(str, enum.Enum):
    BUY_FILL = "buy_fill"
    SELL_FILL = "sell_fill"
    SYNC = "sync"
    ADJUSTMENT = "adjustment"


class SchedulerRunStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class TradeAttemptStatus(str, enum.Enum):
    NOT_ATTEMPTED = "not_attempted"
    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"


class AnalysisRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AnalysisRunType(str, enum.Enum):
    STRATEGY_PERFORMANCE = "strategy_performance"


class AnalysisTargetType(str, enum.Enum):
    STRATEGY_VERSION = "strategy_version"


class AnalysisRunMode(str, enum.Enum):
    SINGLE = "single"
    DUAL = "dual"


class PauseSource(str, enum.Enum):
    RECONCILIATION = "reconciliation"
    ORDER_SYNC = "order_sync"
    MANUAL = "manual"
    RISK_LIMIT = "risk_limit"


class ScannerRuleStatus(str, enum.Enum):
    """스캐너 룰 버전의 상태. 전략 버전과 동일한 라이프사이클(버전 비교 원칙)을 따른다."""

    DRAFT = "draft"
    TESTING = "testing"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ExperimentStatus(str, enum.Enum):
    """Paper 실험의 상태."""

    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class VariantRole(str, enum.Enum):
    """실험 내 전략 버전의 역할 (챔피언/챌린저)."""

    CHAMPION = "champion"
    CHALLENGER = "challenger"


class ScannerConditionType(str, enum.Enum):
    """스캐너 감시 조건 타입. 실제 파라미터는 conditions JSONB에 저장된다."""

    VOLUME_SPIKE = "volume_spike"  # 거래량 급증 (volume_ratio >= multiplier)
    TURNOVER_RANK = "turnover_rank"  # 거래대금 상위 (rank <= max_rank)
    PRICE_CHANGE_PCT = "price_change_pct"  # 상승률 (change_pct >= min_pct)
    INVESTOR_FLOW = "investor_flow"  # 수급 (외국인/기관/개인 순매수·순매도)
    TIME_BUCKET = "time_bucket"  # 시간대 (장초반/오전/오후 등)
