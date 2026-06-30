"""LeaderTrendCandidateEvent repository (M2.15G-4) — 순수 DB 접근, 최소 기능.

**create / get_by_id / list_by_reference_date / exists_by_unique_key 만** 제공한다.
upsert/bulk_create/update/delete 없음 · KIS/broker/http/scheduler import 없음 · 기존 `candidate_events` 미참조.
BaseRepository를 상속하지 않는다(generic update/delete를 노출하지 않기 위해).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.leader_trend_candidate_event import LeaderTrendCandidateEvent


class LeaderTrendCandidateEventRepository:
    """`leader_trend_candidate_events` 전용 read/append-only 저장소(매수 신호 아님)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, event: LeaderTrendCandidateEvent) -> LeaderTrendCandidateEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_id(self, id_: int) -> LeaderTrendCandidateEvent | None:
        return await self.session.get(LeaderTrendCandidateEvent, id_)

    async def list_by_reference_date(
        self, reference_date: date, *, limit: int = 100, offset: int = 0
    ) -> list[LeaderTrendCandidateEvent]:
        stmt = (
            select(LeaderTrendCandidateEvent)
            .where(LeaderTrendCandidateEvent.reference_date == reference_date)
            .order_by(LeaderTrendCandidateEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def exists_by_unique_key(
        self,
        *,
        symbol: str,
        scanner_name: str,
        scanner_version: str,
        reference_date: date,
        timeframe: str,
        window_basis: str,
        universe_scope: str,
    ) -> bool:
        stmt = select(LeaderTrendCandidateEvent.id).where(
            LeaderTrendCandidateEvent.symbol == symbol,
            LeaderTrendCandidateEvent.scanner_name == scanner_name,
            LeaderTrendCandidateEvent.scanner_version == scanner_version,
            LeaderTrendCandidateEvent.reference_date == reference_date,
            LeaderTrendCandidateEvent.timeframe == timeframe,
            LeaderTrendCandidateEvent.window_basis == window_basis,
            LeaderTrendCandidateEvent.universe_scope == universe_scope,
        ).limit(1)
        return (await self.session.execute(stmt)).first() is not None
