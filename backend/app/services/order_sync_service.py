import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.enums import OrderStatus, TradeSide
from app.domain.models.trade import Trade
from app.domain.repositories.trade import TradeRepository
from app.services.position_service import PositionService
from app.trading.broker.base import BrokerClient
from app.trading.broker.error_classifier import classify_exception, exc_message

from app.trading.broker.order_id import normalize_order_id
from app.trading.broker.schemas import OrderExecution
from app.trading.pricing.fees import TradingCostCalculator

logger = logging.getLogger(__name__)


@dataclass
class OrderSyncResult:
    checked: int
    updated: int
    matched: int = 0
    unmatched: int = 0
    unmatched_order_ids: list[str] = field(default_factory=list)
    executions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    error_category: str | None = None
    skipped_reason: str | None = None


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
        self._position_service = PositionService(session)
        settings = get_settings()
        self._cost_calculator = TradingCostCalculator(
            commission_rate=settings.trading_commission_rate,
            sell_tax_rate=settings.trading_sell_tax_rate,
        )

    async def sync_pending_orders(self) -> OrderSyncResult:
        trades = await self._trade_repo.list_pending_or_partial()
        if not trades:
            return OrderSyncResult(checked=0, updated=0, skipped_reason="no_pending_orders")

        try:
            executions = await self._broker.get_daily_executions()
        except Exception as exc:  # noqa: BLE001 - 체결 조회 실패가 scheduler를 죽이면 안 됨
            logger.warning("order sync: get_daily_executions failed: %s", exc)
            return OrderSyncResult(
                checked=len(trades),
                updated=0,
                errors=[exc_message(exc)],
                error_category=classify_exception(exc),
            )

        logger.debug(
            "order sync: fetched %d execution(s): %s",
            len(executions),
            [
                {"odno": e.broker_order_id, "tot_ccld_qty": e.filled_quantity, "ord_qty": e.total_quantity}
                for e in executions
            ],
        )

        executions_by_id = {normalize_order_id(e.broker_order_id): e for e in executions}
        executions_summary = [
            {
                "order_id": e.broker_order_id,
                "filled_quantity": e.filled_quantity,
                "filled_price": float(e.filled_price) if e.filled_price is not None else None,
            }
            for e in executions
        ]

        updated = 0
        matched = 0
        unmatched_order_ids: list[str] = []
        errors: list[str] = []
        for trade in trades:
            execution = executions_by_id.get(normalize_order_id(trade.broker_order_id))
            if execution is None:
                unmatched_order_ids.append(trade.broker_order_id or "")
                continue
            matched += 1
            try:
                updates = _build_trade_updates(trade, execution)
            except Exception as exc:  # noqa: BLE001 - 한 건의 오류가 전체 동기화를 막지 않도록
                logger.warning("order sync: failed to apply trade_id=%s: %s", trade.id, exc)
                errors.append(f"trade_id={trade.id}: {exc}")
                continue

            for key, value in updates.items():
                setattr(trade, key, value)
            updated += 1

            new_fill_quantity = execution.filled_quantity - trade.position_applied_quantity
            if new_fill_quantity > 0 and execution.filled_price is not None:
                fill_cost = self._cost_calculator.calculate(trade.side, execution.filled_price, new_fill_quantity)
                try:
                    await self._position_service.apply_fill(
                        account_id=trade.account_id,
                        symbol_code=trade.symbol_code,
                        symbol_name=trade.symbol_name,
                        side=trade.side,
                        quantity=new_fill_quantity,
                        price=execution.filled_price,
                        commission=fill_cost.commission,
                        tax=fill_cost.tax,
                        trade_id=trade.id,
                        raw=execution.raw,
                    )
                    trade.position_applied_quantity = execution.filled_quantity
                    trade.commission = (trade.commission or Decimal("0")) + fill_cost.commission
                    trade.tax = (trade.tax or Decimal("0")) + fill_cost.tax
                except Exception as exc:  # noqa: BLE001 - 포지션 반영 오류가 전체 동기화를 막지 않도록
                    logger.warning("order sync: failed to apply position for trade_id=%s: %s", trade.id, exc)
                    errors.append(f"trade_id={trade.id} position: {exc}")

            if trade.side == TradeSide.SELL and trade.pnl_amount is not None:
                trade.pnl_amount = trade.pnl_amount - (trade.commission or Decimal("0")) - (trade.tax or Decimal("0"))

        await self._session.commit()
        return OrderSyncResult(
            checked=len(trades),
            updated=updated,
            matched=matched,
            unmatched=len(unmatched_order_ids),
            unmatched_order_ids=unmatched_order_ids,
            executions=executions_summary,
            errors=errors,
        )
