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


class ProposalStatus(str, enum.Enum):
    """AI/수동 제안의 상태. 승인 시에만 새 전략 버전이 생성된다."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ScannerConditionType(str, enum.Enum):
    """스캐너 감시 조건 타입. 실제 파라미터는 conditions JSONB에 저장된다."""

    VOLUME_SPIKE = "volume_spike"  # 거래량 급증 (volume_ratio >= multiplier)
    TURNOVER_RANK = "turnover_rank"  # 거래대금 상위 (rank <= max_rank)
    PRICE_CHANGE_PCT = "price_change_pct"  # 상승률 (change_pct >= min_pct)
    INVESTOR_FLOW = "investor_flow"  # 수급 (외국인/기관/개인 순매수·순매도)
    TIME_BUCKET = "time_bucket"  # 시간대 (장초반/오전/오후 등)


# ── Market Intelligence 어댑터 패턴 (C-2.21.1b) ────────────────────────────

class IntelligenceSourceType(str, enum.Enum):
    """인텔리전스 소스 유형. 데이터가 어떤 종류의 시장 정보인지를 나타낸다."""

    NEWS = "news"
    DISCLOSURE = "disclosure"      # 공시 (DART, EDGAR)
    FINANCIALS = "financials"      # 재무제표
    MARKET_DATA = "market_data"    # 주가/거래량 등 시장 데이터
    MACRO = "macro"                # 거시경제 (FRED, 금리 등)
    POLICY = "policy"              # 정책/규제
    TECH_TREND = "tech_trend"      # 기술/산업 트렌드
    THEME = "theme"                # 테마/섹터
    MANUAL = "manual"              # 수동 입력


class IntelligenceProvider(str, enum.Enum):
    """데이터를 제공하는 외부/내부 provider 식별자."""

    DART = "dart"
    EDGAR = "edgar"
    DARTLAB = "dartlab"
    KIS = "kis"
    RSS = "rss"
    MANUAL = "manual"
    INTERNAL = "internal"
    OTHER = "other"


class IntelligenceMarketScope(str, enum.Enum):
    """소스가 커버하는 시장 범위."""

    KR = "KR"
    US = "US"
    GLOBAL = "GLOBAL"
    MIXED = "MIXED"


class IntelligenceEventStatus(str, enum.Enum):
    """인텔리전스 이벤트 처리 상태."""

    RAW = "raw"              # 수집된 원본
    NORMALIZED = "normalized"  # 정규화 완료
    ASSESSED = "assessed"    # AI 평가 완료
    IGNORED = "ignored"      # 노이즈로 판단, 무시


class IntelligenceCandidateStatus(str, enum.Enum):
    """인텔리전스 기반 후보 처리 상태 (C-2.24)."""

    PENDING = "pending"      # 자동 생성, 검토 대기
    REVIEWED = "reviewed"    # 사람이 검토 완료
    PROMOTED = "promoted"    # 전략 배정 등 다음 단계로 승격
    IGNORED = "ignored"      # 무시 처리


class IntelligenceStrategyProposalStatus(str, enum.Enum):
    """Intelligence 후보 기반 전략 배정 제안 상태 (C-2.26)."""

    PENDING = "pending"      # 자동 생성, 검토 대기
    APPROVED = "approved"    # 사람이 승인 (IntelligenceCandidate → PROMOTED)
    REJECTED = "rejected"    # 사람이 거절
