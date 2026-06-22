from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SchedulerJobOverride(Base):
    """자율 잡(연구/분석)의 사람 지정 활성화 오버라이드.

    행이 없으면 env 기본값(`*_scheduler_enabled`)을 따른다. 행이 있으면 그 값이 우선한다.
    빈 테이블 = 전부 env 기본값(기본 OFF) → 안전 불변식(새 잡 기본 비활성) 유지.
    .env를 못 만지는 상황에서도 웹에서 토글하면 이 테이블에 영속된다.
    """

    __tablename__ = "scheduler_job_overrides"

    job_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
