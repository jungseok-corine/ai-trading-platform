"""C-2.10: 브로커 잔고 기반 포지션 정합성 검사.

동작 원칙:
  - broker.get_broker_positions()로 실시간 보유 종목을 조회한다.
  - DB의 positions 테이블과 symbol 단위로 비교한다.
  - paper 계좌: 불일치 발견 시 DB를 broker 기준으로 동기화한다.
  - real 계좌: 불일치 발견 시 risk_event만 기록하고 DB는 건드리지 않는다.

보안 제약:
  - 실제 주문을 실행하지 않는다.
  - inferred event를 confirmed execution처럼 취급하지 않는다.
  - API key / 계좌번호를 로그에 남기지 않는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, PauseSource, RiskEventResult
from app.domain.repositories.account import AccountRepository
from app.domain.repositories.position import PositionRepository
from app.domain.repositories.risk import RiskEventRepository
from app.services.position_service import PositionService
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import BrokerPositionItem

logger = logging.getLogger(__name__)

# avg_entry_price vs broker average_price 차이 허용 비율 (0.5% 이내는 OK)
_AVG_PRICE_TOLERANCE = Decimal("0.005")


class ReconciliationMismatchType(str, Enum):
    # Broker has qty > 0 but DB has no Position row for this symbol
    BROKER_POSITION_NOT_IN_DB = "broker_position_not_in_db"
    # Broker has qty > 0, DB row exists but quantity = 0
    MISSING_BUY_OR_UNSYNCED_POSITION = "missing_buy_or_unsynced_position"
    # DB has qty > 0, broker response doesn't include this symbol (position may have been closed)
    DB_POSITION_NOT_IN_BROKER = "db_position_not_in_broker"
    # Both sides have the symbol; DB qty > broker qty (possible unsynced sell)
    MISSING_SELL_OR_UNSYNCED_POSITION = "missing_sell_or_unsynced_position"
    # Both sides have the symbol; quantities match but avg prices diverge beyond tolerance
    AVG_PRICE_MISMATCH = "avg_price_mismatch"
    # Quantities match and avg prices are within tolerance — no action needed
    OK = "ok"


@dataclass
class ReconciliationMismatch:
    mismatch_type: ReconciliationMismatchType
    symbol_code: str
    symbol_name: str | None
    db_quantity: int | None
    broker_quantity: int | None
    db_avg_price: Decimal | None
    broker_avg_price: Decimal | None
    details: str


@dataclass
class ReconciliationResult:
    account_id: int
    broker_position_count: int
    db_position_count: int
    comparisons: list[ReconciliationMismatch] = field(default_factory=list)
    synced_to_db: bool = False
    risk_event_created: bool = False
    auto_paused: bool = False

    @property
    def mismatch_count(self) -> int:
        return sum(
            1 for c in self.comparisons
            if c.mismatch_type != ReconciliationMismatchType.OK
        )


class PositionReconciliationService:
    """브로커 잔고와 DB 포지션을 비교해 불일치를 탐지·처리한다."""

    def __init__(self, session: AsyncSession, broker: BrokerClient) -> None:
        self._session = session
        self._broker = broker
        self._account_repo = AccountRepository(session)
        self._position_repo = PositionRepository(session)
        self._risk_event_repo = RiskEventRepository(session)
        self._position_svc = PositionService(session, broker)
        # Lazy import to avoid circular dependency
        self._guard_svc = None

    async def reconcile(self, account_id: int) -> ReconciliationResult:
        """account_id 계좌의 포지션을 브로커 잔고와 비교하고 결과를 반환한다."""
        account = await self._account_repo.get(account_id)
        if account is None:
            raise ValueError(f"account {account_id} not found")

        broker_positions = await self._broker.get_broker_positions()
        db_positions = await self._position_repo.list_by_account(account_id)

        result = ReconciliationResult(
            account_id=account_id,
            broker_position_count=len(broker_positions),
            db_position_count=sum(1 for p in db_positions if p.quantity > 0),
        )

        comparisons = _compare_positions(broker_positions, db_positions)
        result.comparisons = comparisons

        if result.mismatch_count == 0:
            logger.info("reconcile: account=%d no mismatches found", account_id)
            return result

        logger.info(
            "reconcile: account=%d mismatches=%d account_type=%s",
            account_id, result.mismatch_count, account.account_type.value,
        )

        if account.account_type == AccountType.PAPER:
            await self._position_svc.sync_from_broker_positions(account_id)
            result.synced_to_db = True
        else:
            risk_event_id = await self._create_risk_event(account, result)
            result.risk_event_created = True
            await self._auto_pause_real_mode(account_id, result, risk_event_id)
            result.auto_paused = True

        await self._session.commit()
        return result

    async def _auto_pause_real_mode(
        self, account_id: int, result: ReconciliationResult, risk_event_id: int | None
    ) -> None:
        from app.services.trading_guard_service import TradingGuardService  # noqa: PLC0415

        guard_svc = TradingGuardService(self._session)
        non_ok = [c for c in result.comparisons if c.mismatch_type != ReconciliationMismatchType.OK]
        reason = (
            f"{result.mismatch_count} position mismatch(es) in real mode: "
            + "; ".join(f"{c.symbol_code}:{c.mismatch_type.value}" for c in non_ok[:5])
        )
        await guard_svc.auto_pause(
            account_id=account_id,
            reason=reason,
            source=PauseSource.RECONCILIATION,
            risk_event_id=risk_event_id,
        )

    async def _create_risk_event(
        self, account: Account, result: ReconciliationResult
    ) -> int | None:
        non_ok = [c for c in result.comparisons if c.mismatch_type != ReconciliationMismatchType.OK]
        summary = "; ".join(
            f"{c.symbol_code}:{c.mismatch_type.value}"
            f"(db={c.db_quantity},broker={c.broker_quantity})"
            for c in non_ok[:10]  # cap to keep the reason concise
        )
        risk_event = await self._risk_event_repo.create(
            account_id=account.id,
            strategy_version_id=None,
            signal_snapshot={"source": "position_reconciliation"},
            context_snapshot={
                "mismatch_count": result.mismatch_count,
                "broker_position_count": result.broker_position_count,
                "db_position_count": result.db_position_count,
                "mismatches": [
                    {
                        "mismatch_type": c.mismatch_type.value,
                        "symbol_code": c.symbol_code,
                        "db_quantity": c.db_quantity,
                        "broker_quantity": c.broker_quantity,
                        "db_avg_price": str(c.db_avg_price) if c.db_avg_price else None,
                        "broker_avg_price": str(c.broker_avg_price) if c.broker_avg_price else None,
                    }
                    for c in non_ok
                ],
            },
            result=RiskEventResult.REJECTED,
            rule_name="position_reconciliation_mismatch",
            reason=f"{result.mismatch_count} position mismatch(es) detected: {summary}",
        )
        return risk_event.id if risk_event is not None else None


def _compare_positions(
    broker_positions: list[BrokerPositionItem],
    db_positions: list,  # list[Position]
) -> list[ReconciliationMismatch]:
    broker_by_symbol: dict[str, BrokerPositionItem] = {
        p.symbol_code: p for p in broker_positions
    }
    db_by_symbol: dict[str, object] = {p.symbol_code: p for p in db_positions}

    comparisons: list[ReconciliationMismatch] = []

    # Scan broker → check each broker position against DB
    for symbol_code, bp in broker_by_symbol.items():
        dp = db_by_symbol.get(symbol_code)
        if dp is None:
            comparisons.append(ReconciliationMismatch(
                mismatch_type=ReconciliationMismatchType.BROKER_POSITION_NOT_IN_DB,
                symbol_code=symbol_code,
                symbol_name=bp.symbol_name,
                db_quantity=None,
                broker_quantity=bp.quantity,
                db_avg_price=None,
                broker_avg_price=bp.average_price,
                details=f"broker has {bp.quantity} shares but DB has no position row",
            ))
        elif dp.quantity == 0:
            comparisons.append(ReconciliationMismatch(
                mismatch_type=ReconciliationMismatchType.MISSING_BUY_OR_UNSYNCED_POSITION,
                symbol_code=symbol_code,
                symbol_name=bp.symbol_name,
                db_quantity=0,
                broker_quantity=bp.quantity,
                db_avg_price=dp.avg_entry_price,
                broker_avg_price=bp.average_price,
                details=f"broker has {bp.quantity} shares but DB quantity is 0",
            ))
        elif dp.quantity > bp.quantity:
            comparisons.append(ReconciliationMismatch(
                mismatch_type=ReconciliationMismatchType.MISSING_SELL_OR_UNSYNCED_POSITION,
                symbol_code=symbol_code,
                symbol_name=bp.symbol_name,
                db_quantity=dp.quantity,
                broker_quantity=bp.quantity,
                db_avg_price=dp.avg_entry_price,
                broker_avg_price=bp.average_price,
                details=(
                    f"DB qty {dp.quantity} > broker qty {bp.quantity};"
                    " possible unsynced sell"
                ),
            ))
        elif dp.quantity < bp.quantity:
            comparisons.append(ReconciliationMismatch(
                mismatch_type=ReconciliationMismatchType.MISSING_BUY_OR_UNSYNCED_POSITION,
                symbol_code=symbol_code,
                symbol_name=bp.symbol_name,
                db_quantity=dp.quantity,
                broker_quantity=bp.quantity,
                db_avg_price=dp.avg_entry_price,
                broker_avg_price=bp.average_price,
                details=(
                    f"broker qty {bp.quantity} > DB qty {dp.quantity};"
                    " possible unsynced buy"
                ),
            ))
        else:
            # Quantities match — check avg price
            price_diff = _avg_price_diff(dp.avg_entry_price, bp.average_price)
            if price_diff > _AVG_PRICE_TOLERANCE:
                comparisons.append(ReconciliationMismatch(
                    mismatch_type=ReconciliationMismatchType.AVG_PRICE_MISMATCH,
                    symbol_code=symbol_code,
                    symbol_name=bp.symbol_name,
                    db_quantity=dp.quantity,
                    broker_quantity=bp.quantity,
                    db_avg_price=dp.avg_entry_price,
                    broker_avg_price=bp.average_price,
                    details=(
                        f"qty matches ({dp.quantity}) but avg price differs:"
                        f" DB={dp.avg_entry_price} broker={bp.average_price}"
                        f" ({price_diff:.2%})"
                    ),
                ))
            else:
                comparisons.append(ReconciliationMismatch(
                    mismatch_type=ReconciliationMismatchType.OK,
                    symbol_code=symbol_code,
                    symbol_name=bp.symbol_name,
                    db_quantity=dp.quantity,
                    broker_quantity=bp.quantity,
                    db_avg_price=dp.avg_entry_price,
                    broker_avg_price=bp.average_price,
                    details="quantities and avg price match",
                ))

    # Scan DB → catch positions not in broker response (quantity > 0 only)
    for symbol_code, dp in db_by_symbol.items():
        if dp.quantity <= 0:
            continue
        if symbol_code not in broker_by_symbol:
            comparisons.append(ReconciliationMismatch(
                mismatch_type=ReconciliationMismatchType.DB_POSITION_NOT_IN_BROKER,
                symbol_code=symbol_code,
                symbol_name=dp.symbol_name,
                db_quantity=dp.quantity,
                broker_quantity=None,
                db_avg_price=dp.avg_entry_price,
                broker_avg_price=None,
                details=(
                    f"DB has {dp.quantity} shares but broker response has no"
                    " entry for this symbol (position may have been closed)"
                ),
            ))

    return comparisons


def _avg_price_diff(db_price: Decimal, broker_price: Decimal) -> Decimal:
    if broker_price == Decimal("0"):
        return Decimal("0")
    return abs(db_price - broker_price) / broker_price
