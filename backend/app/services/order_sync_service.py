import logging
from dataclasses import dataclass, field
from datetime import datetime
from app.common.timezone import KST
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
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
    stale_cancelled: int = 0
    stale_pending_requires_review: int = 0
    unmatched_order_ids: list[str] = field(default_factory=list)
    executions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    error_category: str | None = None
    skipped_reason: str | None = None


def _is_stale(trade: Trade, market: str = "KR") -> bool:
    """entry_time이 해당 시장의 '이전 거래일'에 속하는 주문을 stale로 판단한다.

    KIS VTS는 지정가 주문을 당일 장 마감에 자동 취소하므로, 전 거래일 이전 주문은
    이미 시장에서 취소된 것으로 간주한다. KR은 KST, US는 미 동부시간(ET) 날짜 기준.
    """
    if trade.entry_time is None:
        return False
    if market == "US":
        from app.common.market_session import ET  # noqa: PLC0415

        today = datetime.now(ET).date()
        entry_date = trade.entry_time.astimezone(ET).date()
    else:
        today = datetime.now(KST).date()
        entry_date = trade.entry_time.astimezone(KST).date()
    return entry_date < today


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


def _merge_result(agg: OrderSyncResult, part: OrderSyncResult) -> None:
    """시장별 동기화 결과를 누적 결과에 합친다(checked는 호출자에서 설정)."""
    agg.updated += part.updated
    agg.matched += part.matched
    agg.unmatched += part.unmatched
    agg.stale_cancelled += part.stale_cancelled
    agg.stale_pending_requires_review += part.stale_pending_requires_review
    agg.unmatched_order_ids.extend(part.unmatched_order_ids)
    agg.executions.extend(part.executions)
    agg.errors.extend(part.errors)
    if agg.error_category is None:
        agg.error_category = part.error_category


class OrderSyncService:
    """KIS 주문체결조회 API로 pending/partial 주문의 실제 체결 상태를 동기화한다.

    TradeService(주문 실행)와는 책임을 분리하며, 체결 조회 실패가 자동매매
    scheduler 전체에 영향을 주지 않도록 예외를 흡수한다.

    Stale pending 정책 (account_type별 분기):
    - PAPER 계좌: KIS VTS 당일 15:30 자동취소 정책에 따라 전날 이전 주문을
      자동으로 CANCELLED 처리한다. 모의투자이므로 실제 손실 위험 없음.
    - LIVE 계좌: 자동 CANCELLED 금지. 체결됐지만 조회 실패한 경우 DB만
      CANCELLED가 되어 실제 포지션과 불일치할 위험이 있다. partial_fill에
      stale_warning을 기록하고 사용자 수동 확인을 요청한다.
      TODO: TTTC8036R (실전) / VTTC8036R (모의) 미체결조회 API를 연동하면
            stale 판단 정확도를 높일 수 있다.
    """

    def __init__(
        self,
        session: AsyncSession,
        broker: BrokerClient,
        overseas_broker: BrokerClient | None = None,
    ) -> None:
        self._session = session
        self._broker = broker
        self._overseas_broker = overseas_broker
        self._trade_repo = TradeRepository(session)
        self._position_service = PositionService(session)
        self._settings = get_settings()

    def _broker_for(self, market: str) -> BrokerClient | None:
        if market == "US":
            return self._overseas_broker
        return self._broker

    async def _get_account_type_map(self, account_ids: set[int]) -> dict[int, AccountType]:
        rows = (
            await self._session.execute(select(Account).where(Account.id.in_(account_ids)))
        ).scalars().all()
        return {a.id: a.account_type for a in rows}

    async def sync_pending_orders(self) -> OrderSyncResult:
        """pending/partial 주문을 시장(KR/US)별로 해당 브로커에서 동기화한다."""
        trades = await self._trade_repo.list_pending_or_partial()
        if not trades:
            return OrderSyncResult(checked=0, updated=0, skipped_reason="no_pending_orders")

        account_type_by_id = await self._get_account_type_map({t.account_id for t in trades})

        # 시장별로 분리해 각 브로커로 동기화한다(US는 해외 브로커, KR은 국내 브로커).
        groups: dict[str, list[Trade]] = {}
        for t in trades:
            groups.setdefault(t.market or "KR", []).append(t)

        agg = OrderSyncResult(checked=len(trades), updated=0)
        for market, group in groups.items():
            broker = self._broker_for(market)
            if broker is None:
                # US 브로커 미구성 등 — 해당 시장 주문은 건너뛴다(에러로 표시).
                agg.errors.append(f"{market} 브로커 미구성 — {len(group)}건 건너뜀")
                continue
            cost_calc = TradingCostCalculator.for_market(market, self._settings)
            res = await self._sync_group(group, broker, market, account_type_by_id, cost_calc)
            _merge_result(agg, res)

        await self._session.commit()
        # 조회 대상(활성 주문)이 전혀 없었으면(전부 stale 처리/조회 불가) 표시한다.
        if agg.matched == 0 and agg.unmatched == 0 and not agg.executions and not agg.errors:
            agg.skipped_reason = "no_active_orders"
        return agg

    async def _sync_group(
        self,
        trades: list[Trade],
        broker: BrokerClient,
        market: str,
        account_type_by_id: dict[int, AccountType],
        cost_calculator: TradingCostCalculator,
    ) -> OrderSyncResult:
        """한 시장(KR 또는 US) 주문 그룹을 해당 브로커로 동기화한다(커밋은 호출자에서)."""
        stale_cancelled = 0
        stale_pending_requires_review = 0
        paper_stale_ids: set[int] = set()

        for trade in trades:
            if not _is_stale(trade, market):
                continue
            # 계좌 유형을 알 수 없으면 실전(LIVE)으로 보수적 처리한다
            account_type = account_type_by_id.get(trade.account_id, AccountType.LIVE)
            if account_type == AccountType.PAPER:
                trade.order_status = OrderStatus.CANCELLED
                trade.partial_fill = {
                    "stale_reason": "auto_cancelled_after_market_close",
                    "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
                }
                paper_stale_ids.add(trade.id)
                stale_cancelled += 1
                logger.info(
                    "order sync: PAPER stale pending auto-cancelled trade_id=%s entry_time=%s",
                    trade.id,
                    trade.entry_time,
                )
            else:
                # LIVE 계좌: 상태 유지, stale_warning 기록
                # KIS 체결조회 결과로 매칭되면 이 warning은 execution.raw로 덮어쓰여진다.
                # TODO: TTTC8036R 미체결조회 API 연동 후 여기서 직접 확인 가능
                trade.partial_fill = {
                    **(trade.partial_fill or {}),
                    "stale_warning": {
                        "detected_at": datetime.now(KST).isoformat(),
                        "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
                        "message": "Unresolved order past market close — manual review required.",
                    },
                }
                stale_pending_requires_review += 1
                logger.warning(
                    "order sync: LIVE account stale pending trade_id=%s entry_time=%s — manual review required",
                    trade.id,
                    trade.entry_time,
                )

        # LIVE stale 주문은 KIS 체결조회에서 해소될 수 있으므로 쿼리 풀에 포함한다.
        # PAPER stale은 자동 취소했으므로 제외한다.
        query_trades = [t for t in trades if t.id not in paper_stale_ids]

        if not query_trades:
            return OrderSyncResult(
                checked=len(trades),
                updated=stale_cancelled,
                stale_cancelled=stale_cancelled,
                stale_pending_requires_review=stale_pending_requires_review,
                skipped_reason="no_active_orders",
            )

        today_kst = datetime.now(KST).date()
        min_date = min(t.entry_time.astimezone(KST).date() for t in query_trades)
        start_date = min_date.strftime("%Y%m%d")
        end_date = today_kst.strftime("%Y%m%d")

        try:
            executions = await broker.get_daily_executions(start_date=start_date, end_date=end_date)
        except Exception as exc:  # noqa: BLE001 - 체결 조회 실패가 scheduler를 죽이면 안 됨
            logger.warning("order sync: get_daily_executions failed (market=%s): %s", market, exc)
            return OrderSyncResult(
                checked=len(trades),
                updated=stale_cancelled,
                stale_cancelled=stale_cancelled,
                stale_pending_requires_review=stale_pending_requires_review,
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

        updated = stale_cancelled
        matched = 0
        unmatched_order_ids: list[str] = []
        errors: list[str] = []
        for trade in query_trades:
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
                fill_cost = cost_calculator.calculate(trade.side, execution.filled_price, new_fill_quantity)
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

        return OrderSyncResult(
            checked=len(trades),
            updated=updated,
            matched=matched,
            unmatched=len(unmatched_order_ids),
            stale_cancelled=stale_cancelled,
            stale_pending_requires_review=stale_pending_requires_review,
            unmatched_order_ids=unmatched_order_ids,
            executions=executions_summary,
            errors=errors,
        )
