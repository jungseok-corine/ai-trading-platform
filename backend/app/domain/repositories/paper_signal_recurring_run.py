from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, select

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

    async def readiness_counts(self, now: datetime) -> dict[str, int]:
        """디스패처 readiness용 **읽기 전용** 집계(M2.14B-3b). 어떤 row도 변경하지 않는다.

        active 하위 분류(exhausted / missing_next / due / not_due)는 상호 배타적이다.
        due = active AND next_run_at IS NOT NULL AND next_run_at <= now AND completed_runs < max_runs.
        """
        m = PaperSignalRecurringRun
        active = m.status == "active"
        not_exhausted = m.completed_runs < m.max_runs
        exhausted = m.completed_runs >= m.max_runs
        has_next = m.next_run_at.is_not(None)
        due = and_(active, not_exhausted, has_next, m.next_run_at <= now)
        not_due = and_(active, not_exhausted, has_next, m.next_run_at > now)
        missing_next = and_(active, not_exhausted, m.next_run_at.is_(None))
        stmt = select(
            func.count().label("total"),
            func.count().filter(m.status == "prepared").label("prepared"),
            func.count().filter(active).label("active"),
            func.count().filter(m.status == "stopped").label("stopped"),
            func.count().filter(m.status == "completed").label("completed"),
            func.count().filter(m.status == "failed").label("failed"),
            func.count().filter(due).label("due_active"),
            func.count().filter(not_due).label("not_due_active"),
            func.count().filter(missing_next).label("active_missing_next_run_at"),
            func.count().filter(and_(active, exhausted)).label("active_exhausted"),
            func.count().filter(m.last_error.is_not(None)).label("with_last_error"),
        )
        row = (await self.session.execute(stmt)).one()
        return {k: int(v) for k, v in row._mapping.items()}

    async def select_due_for_dispatch(
        self, now: datetime, limit: int
    ) -> list[PaperSignalRecurringRun]:
        """디스패처용 **due active** 계획을 선택한다(M2.14B-3c). `paper_signal_recurring_runs`만 스캔.

        due = status=active AND next_run_at IS NOT NULL AND next_run_at <= now AND
              completed_runs < max_runs. PaperSignalSession.active를 스캔하지 않는다(D-27).
        동시 디스패처 패스가 같은 row를 중복 처리하지 않도록 row-lock(FOR UPDATE SKIP LOCKED)을 건다.
        """
        m = PaperSignalRecurringRun
        stmt = (
            select(m)
            .where(
                m.status == "active",
                m.next_run_at.is_not(None),
                m.next_run_at <= now,
                m.completed_runs < m.max_runs,
            )
            .order_by(m.next_run_at.asc(), m.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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
