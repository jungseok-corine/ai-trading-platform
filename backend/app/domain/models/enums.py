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
