from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.investor_flow import InvestorFlow


class InvestorFlowRepository:
    """investor_flows 테이블 read-only 조회 레포지토리.

    전략 실행(SignalService) 등 KIS client 없이 DB 조회만 필요한 경우에 사용한다.
    쓰기(upsert)는 InvestorFlowService.fetch_and_store가 담당한다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_symbol(
        self,
        symbol_code: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[InvestorFlow]:
        """종목 코드와 날짜 범위로 수급 데이터를 조회한다 (최신 날짜 순)."""
        stmt = (
            select(InvestorFlow)
            .where(InvestorFlow.symbol_code == symbol_code)
            .order_by(InvestorFlow.trade_date.desc())
        )
        if date_from is not None:
            stmt = stmt.where(InvestorFlow.trade_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(InvestorFlow.trade_date <= date_to)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
