from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MarketData(Base):
    """OHLCV 시세 데이터.

    추후 TimescaleDB hypertable 전환을 고려해 (symbol_code, timeframe, ts)를
    복합 PK로 사용한다.
    """

    __tablename__ = "market_data"
    __table_args__ = (
        Index("ix_market_data_symbol_timeframe_ts", "symbol_code", "timeframe", "ts"),
    )

    symbol_code: Mapped[str] = mapped_column(String(20), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(10), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)

    open: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
