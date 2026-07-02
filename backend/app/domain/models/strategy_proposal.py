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


class StrategyProposal(Base):
    """전략 개선 제안 (C-2.27).

    AI(또는 사람)가 만든 전략 파라미터 변경 제안을 저장한다. 제안은 바로 적용되지 않고
    pending 상태로 보관되며, 사람이 승인할 때만 새 strategy_version(DRAFT)이 생성된다.
    AI는 직접 전략을 활성화하거나 실거래를 켤 수 없다(문서 2.3 / 13.3).
    """

    __tablename__ = "strategy_proposals"
    __table_args__ = (
        Index("ix_strategy_proposals_strategy_status", "strategy_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )
    # 제안이 기반한 기존 버전 (before 비교용). 없으면 신규 제안.
    base_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="SET NULL")
    )
    # 이 제안을 생성한 AI 분석 run (있으면 추적용)
    ai_analysis_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_analysis_runs.id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)  # 변경 요약
    rationale: Mapped[str | None] = mapped_column(Text)  # 왜 제안하는가 (근거)
    expected_effect: Mapped[str | None] = mapped_column(Text)  # 예상 효과
    risk_notes: Mapped[str | None] = mapped_column(Text)  # 리스크
    suggested_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="ai")
    # base vs proposed 파라미터 백테스트 비교 (C-6.1b). 검토 참고용 — 판정은 사람.
    backtest_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[ProposalStatus] = mapped_column(
        pg_enum(ProposalStatus, "proposal_status"),
        nullable=False,
        default=ProposalStatus.PENDING,
    )
    # 승인 시 생성된 새 버전
    created_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="SET NULL")
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(100))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
