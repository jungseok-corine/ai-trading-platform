from __future__ import annotations

from sqlalchemy import select

from app.domain.models.financial_statement import FinancialStatement
from app.domain.repositories.base import BaseRepository


class FinancialStatementRepository(BaseRepository[FinancialStatement]):
    model = FinancialStatement

    async def get_by_corp_period(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str,
        fs_div: str,
    ) -> FinancialStatement | None:
        result = await self.session.execute(
            select(FinancialStatement).where(
                FinancialStatement.corp_code == corp_code,
                FinancialStatement.bsns_year == bsns_year,
                FinancialStatement.reprt_code == reprt_code,
                FinancialStatement.fs_div == fs_div,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_stock_code(
        self,
        stock_code: str,
        limit: int = 10,
    ) -> list[FinancialStatement]:
        """stock_code의 재무제표를 최신 사업연도 순으로 반환한다."""
        result = await self.session.execute(
            select(FinancialStatement)
            .where(FinancialStatement.stock_code == stock_code)
            .order_by(
                FinancialStatement.bsns_year.desc(),
                FinancialStatement.reprt_code.desc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest_annual(self, stock_code: str) -> FinancialStatement | None:
        """stock_code의 가장 최근 사업보고서(11011) 연결재무제표(CFS)."""
        result = await self.session.execute(
            select(FinancialStatement)
            .where(
                FinancialStatement.stock_code == stock_code,
                FinancialStatement.reprt_code == "11011",
                FinancialStatement.fs_div == "CFS",
            )
            .order_by(FinancialStatement.bsns_year.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
