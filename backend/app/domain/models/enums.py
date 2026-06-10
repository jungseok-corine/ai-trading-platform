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
