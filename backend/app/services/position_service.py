from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import PositionEventType, TradeSide
from app.domain.models.position import Position
from app.domain.repositories.position import PositionRepository
from app.domain.repositories.position_event import PositionEventRepository
from app.trading.broker.base import BrokerClient


def _compute_unrealized_pnl(quantity: int, avg_entry_price: Decimal, last_price: Decimal | None) -> Decimal:
    if quantity == 0 or last_price is None:
        return Decimal("0")
    return (last_price - avg_entry_price) * quantity


class PositionService:
    """계좌-종목 단위 포지션(수량/평단가/손익)을 관리한다.

    OrderSyncService(체결 동기화)와 책임을 분리하며, 순수 계산 로직은
    DB I/O와 분리되어 단위 테스트가 가능하다.
    """

    def __init__(self, session: AsyncSession, broker: BrokerClient | None = None) -> None:
        self._session = session
        self._broker = broker
        self._position_repo = PositionRepository(session)
        self._position_event_repo = PositionEventRepository(session)

    async def apply_fill(
        self,
        *,
        account_id: int,
        symbol_code: str,
        side: TradeSide,
        quantity: int,
        price: Decimal,
        trade_id: int | None = None,
        symbol_name: str | None = None,
        raw: dict | None = None,
    ) -> Position:
        """체결 수량(quantity)만큼 포지션에 반영하고 position_event를 기록한다.

        quantity는 이번에 새로 반영할 체결 수량(델타)이어야 하며, 호출자가
        중복 반영 방지를 책임진다.
        """
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        position = await self._position_repo.get_by_account_symbol(account_id, symbol_code)
        if position is None:
            position = await self._position_repo.create(
                account_id=account_id,
                symbol_code=symbol_code,
                symbol_name=symbol_name,
                quantity=0,
                avg_entry_price=Decimal("0"),
                realized_pnl=Decimal("0"),
                unrealized_pnl=Decimal("0"),
            )
        elif symbol_name is not None and position.symbol_name != symbol_name:
            position.symbol_name = symbol_name

        before_quantity = position.quantity
        before_avg_entry_price = position.avg_entry_price
        realized_pnl_delta: Decimal | None = None

        if side == TradeSide.BUY:
            after_quantity = before_quantity + quantity
            after_avg_entry_price = (
                before_avg_entry_price * before_quantity + price * quantity
            ) / after_quantity
            event_type = PositionEventType.BUY_FILL
            quantity_delta = quantity
        else:
            after_quantity = before_quantity - quantity
            realized_pnl_delta = (price - before_avg_entry_price) * quantity
            after_avg_entry_price = Decimal("0") if after_quantity == 0 else before_avg_entry_price
            position.realized_pnl = position.realized_pnl + realized_pnl_delta
            event_type = PositionEventType.SELL_FILL
            quantity_delta = -quantity

        position.quantity = after_quantity
        position.avg_entry_price = after_avg_entry_price
        position.last_price = price
        position.unrealized_pnl = _compute_unrealized_pnl(after_quantity, after_avg_entry_price, price)

        await self._position_repo.update(position)

        await self._position_event_repo.create(
            position_id=position.id,
            trade_id=trade_id,
            event_type=event_type,
            quantity_delta=quantity_delta,
            price=price,
            realized_pnl_delta=realized_pnl_delta,
            before_quantity=before_quantity,
            after_quantity=after_quantity,
            before_avg_entry_price=before_avg_entry_price,
            after_avg_entry_price=after_avg_entry_price,
            raw=raw,
        )

        await self._session.commit()
        return position

    async def update_last_price(self, account_id: int, symbol_code: str, last_price: Decimal) -> Position | None:
        position = await self._position_repo.get_by_account_symbol(account_id, symbol_code)
        if position is None:
            return None

        position.last_price = last_price
        position.unrealized_pnl = _compute_unrealized_pnl(position.quantity, position.avg_entry_price, last_price)
        await self._position_repo.update(position)
        await self._session.commit()
        return position

    async def refresh_last_price(self, position_id: int) -> Position | None:
        if self._broker is None:
            raise RuntimeError("broker client is required to refresh last_price")

        position = await self._position_repo.get(position_id)
        if position is None:
            return None

        quote = await self._broker.get_current_price(position.symbol_code)
        position.last_price = quote.current_price
        position.unrealized_pnl = _compute_unrealized_pnl(position.quantity, position.avg_entry_price, quote.current_price)
        await self._position_repo.update(position)
        await self._session.commit()
        return position
