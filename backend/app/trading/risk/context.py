from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from app.common.timezone import KST

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import OrderStatus
from app.domain.models.trade import Trade
from app.trading.broker.base import BrokerClient


# 연속 손실 횟수를 계산할 때 조회할 최근 청산 거래 수
CONSECUTIVE_LOSS_LOOKBACK = 20


@dataclass
class RiskContext:
    account_id: int
    account_balance: Decimal
    today_realized_pnl: Decimal
    today_trade_count: int
    open_positions_count: int
    consecutive_losses: int
    current_position_value: dict[str, Decimal] = field(default_factory=dict)
    # USD→KRW 환산 환율 — US 주문 금액을 KRW 한도와 비교할 때 사용(기본 1=환산 없음).
    usd_krw_rate: Decimal = Decimal("1")


class RiskContextBuilder:
    """trades 테이블과 BrokerClient(계좌 잔고)를 조회해 RiskContext를 구성한다."""

    def __init__(self, session: AsyncSession, broker: BrokerClient) -> None:
        self._session = session
        self._broker = broker

    async def build(self, account_id: int) -> RiskContext:
        balance = await self._broker.get_account_balance()
        current_position_value = {
            holding.symbol_code: holding.evaluation_amount for holding in balance.holdings
        }

        today_start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)

        from app.core.config import get_settings  # noqa: PLC0415

        return RiskContext(
            account_id=account_id,
            account_balance=balance.summary.total_deposit,
            today_realized_pnl=await self._sum_today_realized_pnl(account_id, today_start),
            today_trade_count=await self._count_today_trades(account_id, today_start),
            open_positions_count=len(balance.holdings),
            consecutive_losses=await self._count_consecutive_losses(account_id),
            current_position_value=current_position_value,
            usd_krw_rate=get_settings().usd_krw_rate,
        )

    async def _count_today_trades(self, account_id: int, today_start: datetime) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Trade)
            .where(Trade.account_id == account_id)
            .where(Trade.order_status.in_([OrderStatus.FILLED, OrderStatus.PARTIAL]))
            .where(Trade.entry_time >= today_start)
        )
        return result.scalar_one()

    async def _sum_today_realized_pnl(self, account_id: int, today_start: datetime) -> Decimal:
        # 시장(통화)별로 합산한 뒤 US(USD)는 환율로 KRW 환산해 합친다(KRW 한도와 비교용).
        result = await self._session.execute(
            select(Trade.market, func.coalesce(func.sum(Trade.pnl_amount), 0))
            .where(Trade.account_id == account_id)
            .where(Trade.exit_time >= today_start)
            .group_by(Trade.market)
        )
        from app.core.config import get_settings  # noqa: PLC0415

        rate = get_settings().usd_krw_rate
        total = Decimal("0")
        for market, pnl_sum in result.all():
            pnl = Decimal(pnl_sum)
            total += pnl * rate if market == "US" else pnl
        return total

    async def _count_consecutive_losses(self, account_id: int) -> int:
        result = await self._session.execute(
            select(Trade.pnl_amount)
            .where(Trade.account_id == account_id)
            .where(Trade.exit_time.is_not(None))
            .order_by(Trade.exit_time.desc())
            .limit(CONSECUTIVE_LOSS_LOOKBACK)
        )

        consecutive = 0
        for pnl_amount in result.scalars():
            if pnl_amount is not None and pnl_amount < 0:
                consecutive += 1
            else:
                break
        return consecutive
