from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import ExperimentStatus, MarketCode, VariantRole


class Experiment(Base):
    """전략 버전 비교를 위한 paper 실험 (C-2.26).

    여러 strategy_version을 variant로 묶어 동시에 paper에서 비교한다(챔피언/챌린저).
    """

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ExperimentStatus] = mapped_column(
        pg_enum(ExperimentStatus, "experiment_status"),
        nullable=False,
        default=ExperimentStatus.DRAFT,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    variants: Mapped[list["ExperimentVariant"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )


class ExperimentVariant(Base):
    """실험에 포함된 전략 버전(variant). 같은 실험 내에서 strategy_version은 유일하다."""

    __tablename__ = "experiment_variants"
    __table_args__ = (
        UniqueConstraint("experiment_id", "strategy_version_id", name="uq_experiment_variant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False
    )
    strategy_version_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[VariantRole] = mapped_column(
        pg_enum(VariantRole, "variant_role"), nullable=False, default=VariantRole.CHALLENGER
    )
    label: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    experiment: Mapped["Experiment"] = relationship(back_populates="variants")
    results: Mapped[list["ExperimentResult"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan"
    )


class ExperimentResult(Base):
    """variant 성과 지표 스냅샷. compare 실행 시점의 승률/기대값/손익비/낙폭을 보존한다."""

    __tablename__ = "experiment_results"
    __table_args__ = (
        Index("ix_experiment_results_variant", "experiment_variant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_variant_id: Mapped[int] = mapped_column(
        ForeignKey("experiment_variants.id", ondelete="CASCADE"), nullable=False
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    trades_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    avg_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    avg_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    expectancy: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    variant: Mapped["ExperimentVariant"] = relationship(back_populates="results")
