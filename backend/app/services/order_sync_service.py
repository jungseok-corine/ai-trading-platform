import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import OrderStatus, TradeSide
from app.domain.models.trade import Trade
from app.domain.repositories.trade import TradeRepository
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import OrderExecution

logger = logging.getLogger(__name__)


@dataclass
class OrderSyncResult:
    checked: int
    updated: int
    errors: list[str] = field(default_factory=list)


def _build_trade_updates(trade: Trade, execution: OrderExecution) -> dict[str, Any]:
    """체결 조회 결과를 바탕으로 trade에 적용할 변경 사항을 계산한다.

    side 무관하게 partial_fill에는 항상 KIS 응답 원본을 보존한다. 미체결(취소 포함)
    상태에서는 order_status만 갱신한다.
    """
    updates: dict[str, Any] = {"partial_fill": execution.raw}

    if execution.filled_quantity <= 0:
        updates["order_status"] = OrderStatus.CANCELLED if execution.cancelled else OrderStatus.PENDING
        return updates

    updates["order_status"] = (
        OrderStatus.FILLED if execution.filled_quantity >= execution.total_quantity else OrderStatus.PARTIAL
    )

    if trade.side == TradeSide.BUY:
        if execution.filled_price is not None:
            updates["entry_price"] = execution.filled_price
            if trade.entry_price is not None:
                updates["slippage"] = execution.filled_price - trade.entry_price
        if execution.recorded_at is not None:
            updates["entry_time"] = execution.recorded_at
    else:
        if execution.filled_price is not None:
            updates["exit_price"] = execution.filled_price
            if trade.entry_price is not None:
                pnl_amount = (execution.filled_price - trade.entry_price) * execution.filled_quantity
                updates["pnl_amount"] = pnl_amount
                if trade.entry_price != 0:
                    updates["pnl_pct"] = (execution.filled_price - trade.entry_price) / trade.entry_price * 100
        if execution.recorded_at is not None:
            updates["exit_time"] = execution.recorded_at

    return updates


class OrderSyncService:
    """KIS 주문체결조회 API로 pending/partial 주문의 실제 체결 상태를 동기화한다.

    TradeService(주문 실행)와는 책임을 분리하며, 체결 조회 실패가 자동매매
    scheduler 전체에 영향을 주지 않도록 예외를 흡수한다.
    """

    def __init__(self, session: AsyncSession, broker: BrokerClient) -> None:
        self._session = session
        self._broker = broker
        self._trade_repo = TradeRepository(session)

    async def sync_pending_orders(self) -> OrderSyncResult:
        trades = await self._trade_repo.list_pending_or_partial()
        if not trades:
            return OrderSyncResult(checked=0, updated=0)

        try:
            executions = await self._broker.get_daily_executions()
        except Exception as exc:  # noqa: BLE001 - 체결 조회 실패가 scheduler를 죽이면 안 됨
            logger.warning("order sync: get_daily_executions failed: %s", exc)
            return OrderSyncResult(checked=len(trades), updated=0, errors=[str(exc)])

        executions_by_id = {e.broker_order_id: e for e in executions}

        updated = 0
        errors: list[str] = []
        for trade in trades:
            execution = executions_by_id.get(trade.broker_order_id)
            if execution is None:
                continue
            try:
                updates = _build_trade_updates(trade, execution)
            except Exception as exc:  # noqa: BLE001 - 한 건의 오류가 전체 동기화를 막지 않도록
                logger.warning("order sync: failed to apply trade_id=%s: %s", trade.id, exc)
                errors.append(f"trade_id={trade.id}: {exc}")
                continue

            for key, value in updates.items():
                setattr(trade, key, value)
            updated += 1

        await self._session.commit()
        return OrderSyncResult(checked=len(trades), updated=updated, errors=errors)
