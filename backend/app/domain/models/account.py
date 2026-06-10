from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import AccountType


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_type: Mapped[AccountType] = mapped_column(
        pg_enum(AccountType, "account_type"), nullable=False
    )
    broker_account_no: Mapped[str] = mapped_column(String(20), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
