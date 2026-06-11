import enum


class AccountType(str, enum.Enum):
    PAPER = "paper"
    LIVE = "live"


class StrategyVersionStatus(str, enum.Enum):
    DRAFT = "draft"
    TESTING = "testing"
    ACTIVE = "active"
    RETIRED = "retired"


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
