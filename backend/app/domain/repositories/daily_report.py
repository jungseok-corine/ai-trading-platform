from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.domain.models.daily_report import DailyResearchReport
from app.domain.models.enums import MarketCode
from app.domain.repositories.base import BaseRepository


class DailyResearchReportRepository(BaseRepository[DailyResearchReport]):
    model = DailyResearchReport

    async def get_by_date(
        self, market: MarketCode, report_date: date
    ) -> DailyResearchReport | None:
        result = await self.session.execute(
            select(DailyResearchReport).where(
                DailyResearchReport.market == market,
                DailyResearchReport.report_date == report_date,
            )
        )
        return result.scalar_one_or_none()

    async def list_recent(
        self, market: MarketCode | None = None, limit: int = 30
    ) -> list[DailyResearchReport]:
        stmt = select(DailyResearchReport).order_by(
            DailyResearchReport.report_date.desc(), DailyResearchReport.id.desc()
        )
        if market is not None:
            stmt = stmt.where(DailyResearchReport.market == market)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
