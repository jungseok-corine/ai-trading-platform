from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    symbols: Mapped[list["WatchlistSymbol"]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan"
    )


class WatchlistSymbol(Base):
    __tablename__ = "watchlist_symbols"
    __table_args__ = (UniqueConstraint("watchlist_id", "symbol_code", name="uq_watchlist_symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False
    )
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol_name: Mapped[str | None] = mapped_column(String(100))
    # 멀티마켓: 시장 구분(KR/US)과 미국 거래소 코드(NAS/NYS/AMS). enum 없이 String.
    market: Mapped[str] = mapped_column(String(2), nullable=False, server_default="KR")
    exchange: Mapped[str | None] = mapped_column(String(8))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    watchlist: Mapped["Watchlist"] = relationship(back_populates="symbols")
