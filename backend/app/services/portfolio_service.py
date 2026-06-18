from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.position import PositionRepository
from app.trading.position.schemas import PortfolioSummaryRead


class PortfolioService:
    """계좌 단위 포지션을 합산해 포트폴리오 요약(보유수량/손익)을 계산한다."""

    def __init__(self, session: AsyncSession) -> None:
        self._position_repo = PositionRepository(session)

    async def get_summary(self, account_id: int) -> PortfolioSummaryRead:
        # include_closed=True: realized_pnl은 이미 매도된 포지션 포함해 누적 합산
        all_positions = await self._position_repo.list_by_account(account_id, include_closed=True)
        held = [p for p in all_positions if p.quantity != 0]

        total_quantity = sum(p.quantity for p in held)
        total_cost_amount = sum((p.avg_entry_price * p.quantity for p in held), Decimal("0"))
        total_eval_amount = sum(
            ((p.last_price if p.last_price is not None else p.avg_entry_price) * p.quantity for p in held),
            Decimal("0"),
        )
        # unrealized_pnl: 현재 보유 중인 포지션의 평가손익만 합산 (매도완료 제외)
        total_unrealized_pnl = sum((p.unrealized_pnl for p in held), Decimal("0"))
        # realized_pnl: 전체 누적 실현손익 (매도완료 포지션 포함)
        total_realized_pnl = sum((p.realized_pnl for p in all_positions), Decimal("0"))
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
