from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import AnalysisRunStatus, AnalysisRunType, AnalysisTargetType


class AiAnalysisRun(Base):
    """AI provider를 이용한 단일 분석 실행 기록."""

    __tablename__ = "ai_analysis_runs"
    __table_args__ = (
        Index("ix_ai_analysis_runs_strategy_version_id", "strategy_version_id"),
        Index("ix_ai_analysis_runs_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_type: Mapped[AnalysisRunType] = mapped_column(
        pg_enum(AnalysisRunType, "analysis_run_type"), nullable=False
    )
    target_type: Mapped[AnalysisTargetType] = mapped_column(
        pg_enum(AnalysisTargetType, "analysis_target_type"), nullable=False
    )
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True
    )
    strategy_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="SET NULL"), nullable=True
    )
    prompt_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[AnalysisRunStatus] = mapped_column(
        pg_enum(AnalysisRunStatus, "analysis_run_status"), nullable=False
    )
    input_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warnings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    responses: Mapped[list["AiModelResponse"]] = relationship(
        "AiModelResponse",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class AiModelResponse(Base):
    """AI provider의 개별 응답 기록."""

    __tablename__ = "ai_model_responses"
    __table_args__ = (Index("ix_ai_model_responses_run_id", "run_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("ai_analysis_runs.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)   # primary_analysis / synthesis / ...
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped["AiAnalysisRun"] = relationship("AiAnalysisRun", back_populates="responses")
