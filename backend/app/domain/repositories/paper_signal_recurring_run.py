from __future__ import annotations

from sqlalchemy import select

from app.domain.models.paper_signal_recurring_run import PaperSignalRecurringRun
from app.domain.repositories.base import BaseRepository

# 비종료(non-terminal) 상태 — 중복 계획 가드에 쓴다.
NON_TERMINAL_STATUSES = ("prepared", "active")


class PaperSignalRecurringRunRepository(BaseRepository[PaperSignalRecurringRun]):
    model = PaperSignalRecurringRun

    async def list_filtered(
        self, status: str | None = None, limit: int = 200, offset: int = 0
    ) -> list[PaperSignalRecurringRun]:
        stmt = select(PaperSignalRecurringRun).order_by(PaperSignalRecurringRun.id.desc())
        if status is not None:
            stmt = stmt.where(PaperSignalRecurringRun.status == status)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_open_for_pair(
        self, baseline_session_id: int, challenger_session_id: int
    ) -> PaperSignalRecurringRun | None:
        """같은 페어에 대한 **비종료(prepared/active)** 계획을 찾는다(중복 생성 가드).

        stopped/completed/failed 계획은 제외 → 종료된 계획이 있어도 새 prepared 계획은 허용된다.
        """
        result = await self.session.execute(
            select(PaperSignalRecurringRun).where(
                PaperSignalRecurringRun.baseline_session_id == baseline_session_id,
                PaperSignalRecurringRun.challenger_session_id == challenger_session_id,
                PaperSignalRecurringRun.status.in_(NON_TERMINAL_STATUSES),
            )
        )
        return result.scalars().first()

    async def find_active_for_pair(
        self,
        baseline_session_id: int,
        challenger_session_id: int,
        exclude_id: int | None = None,
    ) -> PaperSignalRecurringRun | None:
        """같은 페어에 대한 **active** 계획을 찾는다(활성화 시 중복 active 가드, 자기 제외)."""
        stmt = select(PaperSignalRecurringRun).where(
            PaperSignalRecurringRun.baseline_session_id == baseline_session_id,
            PaperSignalRecurringRun.challenger_session_id == challenger_session_id,
            PaperSignalRecurringRun.status == "active",
        )
        if exclude_id is not None:
            stmt = stmt.where(PaperSignalRecurringRun.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()
