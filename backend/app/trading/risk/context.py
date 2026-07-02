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

# RISK-FIX-1E: consecutive loss streak는 "실질 가격 방향 손실"만 센다.
# 방향 손익률(directional return)이 이 epsilon(절대값) 이내이면 break-even으로 보고 손실로 세지 않는다.
# 단위: pnl_pct는 (exit_price - entry_price) / entry_price * 100 로 계산되는 percent point(수수료 미포함)다.
# 따라서 0.01 = 0.01%p. 수수료/세금만으로 pnl_amount<0인 fee-only break-even 청산을 제외하기 위한 값이다.
CONSECUTIVE_LOSS_BREAK_EVEN_EPSILON_PCT = Decimal("0.01")


def _is_directional_streak_loss(
    pnl_amount: Decimal | None,
    pnl_pct: Decimal | None,
    entry_price: Decimal | None,
    exit_price: Decimal | None,
    *,
    epsilon_pct: Decimal = CONSECUTIVE_LOSS_BREAK_EVEN_EPSILON_PCT,
) -> bool:
    """연속 손실 streak에 포함할 "실질 가격 방향 손실"인지 판정한다(RISK-FIX-1E).

    - 1순위: 방향 손익률 pnl_pct(수수료 미포함). 없으면 entry/exit price로 계산.
    - directional_return_pct < -epsilon → 손실로 카운트.
    - |directional_return_pct| <= epsilon → fee-only/near-flat break-even → 손실 아님.
    - 방향 데이터가 전혀 없으면 보수적으로 pnl_amount < 0 으로 판단(기존 동작 fallback).
    """
    directional_pct = pnl_pct
    if (
        directional_pct is None
        and entry_price is not None
        and exit_price is not None
        and entry_price != 0
    ):
        directional_pct = (exit_price - entry_price) / entry_price * 100
    if directional_pct is not None:
        return directional_pct < -epsilon_pct
    # 방향 판단 불가 → 보수적 fallback(실제 자본 손실 기준).
    return pnl_amount is not None and pnl_amount < 0


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
    # 인트라데이 변동성 레짐 (C-6.5 soft kill용). None = soft kill 비활성(기본) 또는 조회 실패
    # — None이면 VolatilitySoftKillRule이 항상 통과하므로 안전 기본값이 유지된다.
    intraday_regime: str | None = None


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

        settings = get_settings()
        return RiskContext(
            account_id=account_id,
            account_balance=balance.summary.total_deposit,
            today_realized_pnl=await self._sum_today_realized_pnl(account_id, today_start),
            today_trade_count=await self._count_today_trades(account_id, today_start),
            open_positions_count=len(balance.holdings),
            consecutive_losses=await self._count_consecutive_losses(account_id),
            current_position_value=current_position_value,
            usd_krw_rate=settings.usd_krw_rate,
            intraday_regime=await self._fetch_regime(settings),
        )

    async def _fetch_regime(self, settings) -> str | None:
        """soft kill(C-6.5) 게이트가 켜졌을 때만 레짐을 조회한다. 실패 시 None(통과)."""
        if not settings.volatility_soft_kill_enabled:
            return None
        try:
            from app.services.intraday_regime_service import IntradayRegimeService  # noqa: PLC0415

            snap = await IntradayRegimeService(self._session).snapshot()
            return snap.regime
        except Exception:  # noqa: BLE001 - 레짐 조회 실패가 리스크 검증을 중단시키지 않도록
            return None

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
        # RISK-FIX-1E: pnl_amount<0만 보지 않고, 방향 손익률(pnl_pct / entry·exit price) 기준으로
        # 실질 가격 방향 손실만 센다. fee-only break-even 청산은 streak에서 제외한다.
        result = await self._session.execute(
            select(Trade.pnl_amount, Trade.pnl_pct, Trade.entry_price, Trade.exit_price)
            .where(Trade.account_id == account_id)
            .where(Trade.exit_time.is_not(None))
            .order_by(Trade.exit_time.desc())
            .limit(CONSECUTIVE_LOSS_LOOKBACK)
        )

        consecutive = 0
        for pnl_amount, pnl_pct, entry_price, exit_price in result.all():
            if _is_directional_streak_loss(pnl_amount, pnl_pct, entry_price, exit_price):
                consecutive += 1
            else:
                break
        return consecutive
