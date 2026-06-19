from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import MarketCode, ScannerRuleStatus


class ScannerRule(Base):
    """시장 감시 룰의 원형(컨테이너). 실제 조건은 버전(ScannerRuleVersion)에 담긴다.

    전략(Strategy)과 동일하게, 룰 자체는 종목을 직접 갖지 않고 '어떤 종목을 감시 대상으로
    올릴지'를 정의한다. market 필드로 한국장/미국장을 구분한다.
    """

    __tablename__ = "scanner_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    versions: Mapped[list["ScannerRuleVersion"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )


class ScannerRuleVersion(Base):
    """스캐너 룰의 버전. 감시 조건 리스트를 JSONB로 저장한다.

    버전 비교 원칙(2.2)에 따라 룰 개선은 새 버전으로 만들어 기존 버전과 비교한다.
    conditions 예:
      [{"type":"volume_spike","params":{"window":20,"multiplier":2.0}},
       {"type":"price_change_pct","params":{"min_pct":5.0}}]
    """

    __tablename__ = "scanner_rule_versions"
    __table_args__ = (
        UniqueConstraint("scanner_rule_id", "version_no", name="uq_scanner_rule_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scanner_rule_id: Mapped[int] = mapped_column(
        ForeignKey("scanner_rules.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[ScannerRuleStatus] = mapped_column(
        pg_enum(ScannerRuleStatus, "scanner_rule_status"),
        nullable=False,
        default=ScannerRuleStatus.DRAFT,
    )
    change_description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    rule: Mapped["ScannerRule"] = relationship(back_populates="versions")
