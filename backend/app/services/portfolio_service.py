from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.position import PositionRepository
from app.trading.position.schemas import PortfolioSummaryRead


class PortfolioService:
    """계좌 단위 포지션을 합산해 포트폴리오 요약(보유수량/손익)을 계산한다."""

    def __init__(self, session: AsyncSession) -> None:
        self._position_repo = PositionRepository(session)

    async def get_summary(self, account_id: int) -> PortfolioSummaryRead:
        positions = await self._position_repo.list_by_account(account_id)

        held = [p for p in positions if p.quantity != 0]

        total_quantity = sum(p.quantity for p in held)
        total_cost_amount = sum((p.avg_entry_price * p.quantity for p in held), Decimal("0"))
        total_eval_amount = sum(
            ((p.last_price if p.last_price is not None else p.avg_entry_price) * p.quantity for p in held),
            Decimal("0"),
        )
        total_unrealized_pnl = sum((p.unrealized_pnl for p in positions), Decimal("0"))
        total_realized_pnl = sum((p.realized_pnl for p in positions), Decimal("0"))
        total_unrealized_pnl_pct = (
            (total_unrealized_pnl / total_cost_amount * 100) if total_cost_amount != 0 else Decimal("0")
        )

        return PortfolioSummaryRead(
            account_id=account_id,
            position_count=len(held),
            total_quantity=total_quantity,
            total_cost_amount=total_cost_amount,
            total_eval_amount=total_eval_amount,
            total_unrealized_pnl=total_unrealized_pnl,
            total_unrealized_pnl_pct=total_unrealized_pnl_pct,
            total_realized_pnl=total_realized_pnl,
            total_pnl=total_unrealized_pnl + total_realized_pnl,
        )
