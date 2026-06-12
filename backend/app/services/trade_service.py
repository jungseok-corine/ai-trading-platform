import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.trade import Trade
from app.domain.repositories.trade import TradeRepository
from app.services.risk_service import RiskService
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import OrderRequest, OrderType
from app.trading.order.schemas import OrderCreateRequest
from app.trading.pricing.tick import round_price_to_tick
from app.trading.strategy.base import Signal

logger = logging.getLogger(__name__)


@dataclass
class OrderPlacementResult:
    approved: bool
    trade: Trade | None
    rule_name: str | None = None
    reason: str | None = None


class TradeService:
    """Signal을 RiskManager 검증 후 BrokerClient를 통해 실행하고 trades에 기록한다.

    수동 주문(API)과 자동 주문(StrategyRunnerService)이 모두 execute_signal()을
    통해 동일한 RiskManager/주문 실행 경로를 거친다.
    """

    def __init__(self, session: AsyncSession, broker: BrokerClient, risk_service: RiskService) -> None:
        self._session = session
        self._broker = broker
        self._risk_service = risk_service
        self._trade_repo = TradeRepository(session)

    async def place_order(self, request: OrderCreateRequest) -> OrderPlacementResult:
        signal = Signal(
            symbol_code=request.symbol_code,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            reason=request.reason or "",
            strategy_version_id=request.strategy_version_id,
        )
        return await self.execute_signal(
            request.account_id, signal, order_type=request.order_type, reason_source="manual"
        )

    async def execute_signal(
        self,
        account_id: int,
        signal: Signal,
        order_type: OrderType = OrderType.LIMIT,
        reason_source: str = "manual",
    ) -> OrderPlacementResult:
        """Signal을 RiskManager로 검증 후 승인되면 주문을 실행하고 trades에 기록한다.

        거부되면 trades는 저장하지 않는다 (risk_events는 RiskService가 기록).
        """
        logger.info(
            "execute_signal start: source=%s account_id=%s symbol=%s side=%s qty=%s price=%s",
            reason_source, account_id, signal.symbol_code, signal.side, signal.quantity, signal.price,
        )

        risk_result = await self._risk_service.validate_signal(account_id, signal)
        if not risk_result.approved:
            logger.info(
                "execute_signal rejected: source=%s account_id=%s rule=%s reason=%s",
                reason_source, account_id, risk_result.rule_name, risk_result.reason,
            )
            return OrderPlacementResult(
                approved=False,
                trade=None,
                rule_name=risk_result.rule_name,
                reason=risk_result.reason,
            )

        adjusted_price = signal.price
        market_condition: dict | None = None
        if order_type == OrderType.LIMIT:
            adjusted_price = round_price_to_tick(signal.price, signal.side)
            if adjusted_price != signal.price:
                logger.info(
                    "price tick adjustment: source=%s symbol=%s side=%s original_price=%s adjusted_price=%s",
                    reason_source, signal.symbol_code, signal.side, signal.price, adjusted_price,
                )
            market_condition = {
                "price_tick_adjustment": {
                    "original_price": str(signal.price),
                    "adjusted_price": str(adjusted_price),
                }
            }

        order_result = await self._broker.place_order(
            OrderRequest(
                symbol_code=signal.symbol_code,
                side=signal.side,
                quantity=signal.quantity,
                price=adjusted_price,
                order_type=order_type,
            )
        )

        trade = await self._trade_repo.create(
            account_id=account_id,
            strategy_version_id=signal.strategy_version_id,
            symbol_code=signal.symbol_code,
            side=signal.side,
            entry_time=order_result.ordered_at,
            entry_price=adjusted_price,
            quantity=signal.quantity,
            entry_reason=signal.reason,
            market_condition=market_condition,
            order_status=order_result.order_status,
            broker_order_id=order_result.broker_order_id,
        )
        await self._session.commit()
        logger.info(
            "execute_signal approved: source=%s account_id=%s trade_id=%s broker_order_id=%s",
            reason_source, account_id, trade.id, order_result.broker_order_id,
        )
        return OrderPlacementResult(approved=True, trade=trade)

    async def list_trades(self, account_id: int | None, limit: int, offset: int) -> list[Trade]:
        if account_id is not None:
            return await self._trade_repo.list_by_account(account_id, limit, offset)
        return await self._trade_repo.list(limit, offset)

    async def get_trade(self, trade_id: int) -> Trade | None:
        return await self._trade_repo.get(trade_id)
