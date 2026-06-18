from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import PositionEventType, TradeSide
from app.domain.models.position import Position
from app.domain.repositories.position import PositionRepository
from app.domain.repositories.position_event import PositionEventRepository
from app.trading.broker.base import BrokerClient


@dataclass
class PositionMismatch:
    position_id: int
    symbol_code: str
    account_id: int
    position_quantity: int
    event_quantity_sum: int
    discrepancy: int


def _compute_unrealized_pnl(quantity: int, avg_entry_price: Decimal, last_price: Decimal | None) -> Decimal:
    if quantity == 0 or last_price is None:
        return Decimal("0")
    return (last_price - avg_entry_price) * quantity


@dataclass
class BrokerPositionSyncResult:
    created: int = 0
    updated: int = 0
    zeroed: int = 0
    positions: list[Position] = field(default_factory=list)


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
        commission: Decimal = Decimal("0"),
        tax: Decimal = Decimal("0"),
        trade_id: int | None = None,
        symbol_name: str | None = None,
        raw: dict | None = None,
    ) -> Position:
        """체결 수량(quantity)만큼 포지션에 반영하고 position_event를 기록한다.

        quantity는 이번에 새로 반영할 체결 수량(델타)이어야 하며, 호출자가
        중복 반영 방지를 책임진다.

        commission/tax는 이번 체결분에 대한 수수료/세금(원)이다.
        - BUY: commission을 매입 단가에 가산해 avg_entry_price(평단가)의 비용에 포함시킨다
          (세금은 매수 시 부과되지 않는다).
        - SELL: realized_pnl_delta(매도가 - 평단가 기준 gross 손익)에서 commission+tax를
          차감한 realized_pnl_delta_net을 positions.realized_pnl에 누적한다.
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
        realized_pnl_delta_net: Decimal | None = None

        if side == TradeSide.BUY:
            after_quantity = before_quantity + quantity
            cost_per_share = price + (commission / quantity)
            after_avg_entry_price = (
                before_avg_entry_price * before_quantity + cost_per_share * quantity
            ) / after_quantity
            event_type = PositionEventType.BUY_FILL
            quantity_delta = quantity
        else:
            after_quantity = before_quantity - quantity
            realized_pnl_delta = (price - before_avg_entry_price) * quantity
            realized_pnl_delta_net = realized_pnl_delta - commission - tax
            after_avg_entry_price = Decimal("0") if after_quantity == 0 else before_avg_entry_price
            position.realized_pnl = position.realized_pnl + realized_pnl_delta_net
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
            realized_pnl_delta_net=realized_pnl_delta_net,
            commission=commission,
            tax=tax,
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

    async def sync_from_broker_positions(self, account_id: int) -> BrokerPositionSyncResult:
        """KIS 잔고조회 결과를 기준으로 내부 positions를 보정한다.

        - KIS에는 있는데 내부에 없는 종목: 새로 생성 (realized_pnl=0부터 시작).
        - KIS와 내부에 모두 있는 종목: quantity/avg_entry_price/last_price/symbol_name/
          unrealized_pnl을 KIS 값으로 덮어쓴다. realized_pnl(내부 체결 기록 기준)은
          유지한다.
        - 내부에는 있는데 KIS에는 없는 종목(quantity != 0): KIS 기준 실제 보유가
          없다는 뜻이므로 quantity=0, unrealized_pnl=0으로 보정한다. avg_entry_price와
          realized_pnl은 과거 체결 이력 참고용으로 유지한다.
        """
        if self._broker is None:
            raise RuntimeError("broker client is required to sync positions from broker")

        holdings = await self._broker.get_account_positions()
        holdings_by_symbol = {h.symbol_code: h for h in holdings}

        # qty=0 포지션도 포함 — 이미 row가 있는데 새로 create하면 unique constraint 위반
        existing = await self._position_repo.list_by_account(account_id, include_closed=True)
        existing_by_symbol = {p.symbol_code: p for p in existing}

        result = BrokerPositionSyncResult()

        for symbol_code, holding in holdings_by_symbol.items():
            unrealized_pnl = _compute_unrealized_pnl(
                holding.quantity, holding.avg_purchase_price, holding.current_price
            )
            position = existing_by_symbol.get(symbol_code)
            if position is None:
                new_position = await self._position_repo.create(
                    account_id=account_id,
                    symbol_code=symbol_code,
                    symbol_name=holding.symbol_name,
                    quantity=holding.quantity,
                    avg_entry_price=holding.avg_purchase_price,
                    last_price=holding.current_price,
                    unrealized_pnl=unrealized_pnl,
                    realized_pnl=Decimal("0"),
                )
                await self._position_event_repo.create(
                    position_id=new_position.id,
                    trade_id=None,
                    event_type=PositionEventType.SYNC,
                    quantity_delta=holding.quantity,
                    price=holding.current_price,
                    realized_pnl_delta=None,
                    realized_pnl_delta_net=None,
                    commission=None,
                    tax=None,
                    before_quantity=0,
                    after_quantity=holding.quantity,
                    before_avg_entry_price=Decimal("0"),
                    after_avg_entry_price=holding.avg_purchase_price,
                    raw={"source": "broker_sync"},
                )
                result.created += 1
            else:
                before_quantity = position.quantity
                before_avg_entry_price = position.avg_entry_price
                position.symbol_name = holding.symbol_name
                position.quantity = holding.quantity
                position.avg_entry_price = holding.avg_purchase_price
                position.last_price = holding.current_price
                position.unrealized_pnl = unrealized_pnl
                await self._position_repo.update(position)
                await self._position_event_repo.create(
                    position_id=position.id,
                    trade_id=None,
                    event_type=PositionEventType.SYNC,
                    quantity_delta=holding.quantity - before_quantity,
                    price=holding.current_price,
                    realized_pnl_delta=None,
                    realized_pnl_delta_net=None,
                    commission=None,
                    tax=None,
                    before_quantity=before_quantity,
                    after_quantity=holding.quantity,
                    before_avg_entry_price=before_avg_entry_price,
                    after_avg_entry_price=holding.avg_purchase_price,
                    raw={"source": "broker_sync"},
                )
                result.updated += 1

        for symbol_code, position in existing_by_symbol.items():
            if symbol_code in holdings_by_symbol or position.quantity == 0:
                continue
            before_quantity = position.quantity
            position.quantity = 0
            position.unrealized_pnl = Decimal("0")
            await self._position_repo.update(position)
            await self._position_event_repo.create(
                position_id=position.id,
                trade_id=None,
                event_type=PositionEventType.SYNC,
                quantity_delta=-before_quantity,
                price=position.last_price,
                realized_pnl_delta=None,
                realized_pnl_delta_net=None,
                commission=None,
                tax=None,
                before_quantity=before_quantity,
                after_quantity=0,
                before_avg_entry_price=position.avg_entry_price,
                after_avg_entry_price=position.avg_entry_price,
                raw={"source": "broker_sync"},
            )
            result.zeroed += 1

        await self._session.commit()
        result.positions = await self._position_repo.list_by_account(account_id)
        return result

    async def diagnose_position_mismatch(self, account_id: int) -> list[PositionMismatch]:
        """positions.quantity와 position_events.quantity_delta 합산을 비교해 불일치를 탐지한다.

        position_events 기록 없이 positions이 직접 수정된 경우(예: 과거 broker sync)를 감지한다.
        반환 목록이 비어 있으면 position_events로 현재 수량이 완전히 설명된다.
        """
        positions = await self._position_repo.list_by_account(account_id, include_closed=True)
        mismatches: list[PositionMismatch] = []
        for position in positions:
            events = await self._position_event_repo.list_by_position(position.id, limit=10000)
            event_sum = sum(e.quantity_delta for e in events)
            if position.quantity != event_sum:
                mismatches.append(
                    PositionMismatch(
                        position_id=position.id,
                        symbol_code=position.symbol_code,
                        account_id=account_id,
                        position_quantity=position.quantity,
                        event_quantity_sum=event_sum,
                        discrepancy=position.quantity - event_sum,
                    )
                )
        return mismatches

    async def refresh_all_prices(self, account_id: int) -> list[Position]:
        """계좌의 보유수량(quantity != 0) 포지션의 현재가를 모두 갱신하고 평가손익을 재계산한다.

        quantity == 0인 포지션은 평가금액 계산 대상이 아니므로 시세 조회를 생략한다.
        """
        if self._broker is None:
            raise RuntimeError("broker client is required to refresh prices")

        positions = await self._position_repo.list_by_account(account_id)
        updated: list[Position] = []
        for position in positions:
            if position.quantity == 0:
                continue
            quote = await self._broker.get_current_price(position.symbol_code)
            position.last_price = quote.current_price
            position.unrealized_pnl = _compute_unrealized_pnl(
                position.quantity, position.avg_entry_price, quote.current_price
            )
            await self._position_repo.update(position)
            updated.append(position)

        if updated:
            await self._session.commit()
        return updated
