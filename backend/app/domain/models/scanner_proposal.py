from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import ProposalStatus


class ScannerRuleProposal(Base):
    """스캐너 룰 개선 제안 (C-2.39).

    후보 성과 분석(C-2.38)을 근거로 AI(또는 사람)가 만든 '스캐너 조건 강화' 제안을 저장한다.
    전략 제안(StrategyProposal)과 동일하게 바로 적용되지 않고 pending 상태로 보관되며,
    사람이 승인할 때만 새 scanner_rule_version(DRAFT)이 생성된다. AI는 직접 룰을
    활성화하거나 실거래를 켤 수 없다(문서 2.3 / 13.3).
    """

    __tablename__ = "scanner_rule_proposals"
    __table_args__ = (
        Index("ix_scanner_rule_proposals_rule_status", "scanner_rule_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scanner_rule_id: Mapped[int] = mapped_column(
        ForeignKey("scanner_rules.id", ondelete="CASCADE"), nullable=False
    )
    # 제안이 기반한 기존 룰 버전 (before 비교용 / 성과 분석 대상).
    base_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("scanner_rule_versions.id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)  # 변경 요약
    rationale: Mapped[str | None] = mapped_column(Text)  # 왜 제안하는가 (근거)
    expected_effect: Mapped[str | None] = mapped_column(Text)  # 예상 효과
    risk_notes: Mapped[str | None] = mapped_column(Text)  # 리스크
    suggested_conditions: Mapped[list] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="ai")

    status: Mapped[ProposalStatus] = mapped_column(
        pg_enum(ProposalStatus, "proposal_status"),
        nullable=False,
        default=ProposalStatus.PENDING,
    )
    # 승인 시 생성된 새 룰 버전
    created_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("scanner_rule_versions.id", ondelete="SET NULL")
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(100))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
