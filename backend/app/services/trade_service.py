from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.trade import Trade
from app.domain.repositories.trade import TradeRepository
from app.services.risk_service import RiskService
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import OrderRequest
from app.trading.order.schemas import OrderCreateRequest
from app.trading.strategy.base import Signal


@dataclass
class OrderPlacementResult:
    approved: bool
    trade: Trade | None
    rule_name: str | None = None
    reason: str | None = None


class TradeService:
    """주문 요청을 RiskManager 검증 후 BrokerClient를 통해 실행하고 trades에 기록한다."""

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

        risk_result = await self._risk_service.validate_signal(request.account_id, signal)
        if not risk_result.approved:
            return OrderPlacementResult(
                approved=False,
                trade=None,
                rule_name=risk_result.rule_name,
                reason=risk_result.reason,
            )

        order_result = await self._broker.place_order(
            OrderRequest(
                symbol_code=request.symbol_code,
                side=request.side,
                quantity=request.quantity,
                price=request.price,
                order_type=request.order_type,
            )
        )

        trade = await self._trade_repo.create(
            account_id=request.account_id,
            strategy_version_id=request.strategy_version_id,
            symbol_code=request.symbol_code,
            side=request.side,
            entry_time=order_result.ordered_at,
            entry_price=request.price,
            quantity=request.quantity,
            entry_reason=request.reason,
            order_status=order_result.order_status,
            broker_order_id=order_result.broker_order_id,
        )
        await self._session.commit()
        return OrderPlacementResult(approved=True, trade=trade)

    async def list_trades(self, account_id: int | None, limit: int, offset: int) -> list[Trade]:
        if account_id is not None:
            return await self._trade_repo.list_by_account(account_id, limit, offset)
        return await self._trade_repo.list(limit, offset)

    async def get_trade(self, trade_id: int) -> Trade | None:
        return await self._trade_repo.get(trade_id)
