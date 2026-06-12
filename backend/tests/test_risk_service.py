from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, RiskEventResult, TradeSide
from app.domain.models.risk import RiskConfig, RiskEvent
from app.services.risk_service import RiskService
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import (
    AccountBalance,
    AccountHolding,
    AccountSummary,
    MinuteCandle,
    OrderExecution,
    OrderRequest,
    OrderResult,
    PriceQuote,
)
from app.trading.strategy.base import Signal


class FakeBrokerClient(BrokerClient):
    """RiskContextBuilder 테스트용 — 항상 고정된 잔고/보유종목 없음을 반환."""

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        raise NotImplementedError

    async def get_account_balance(self) -> AccountBalance:
        return AccountBalance(
            holdings=[],
            summary=AccountSummary(
                total_deposit=Decimal("10000000"),
                total_purchase_amount=Decimal("0"),
                total_evaluation_amount=Decimal("0"),
                total_profit_loss_amount=Decimal("0"),
            ),
        )

    async def get_account_positions(self) -> list[AccountHolding]:
        return []

    async def place_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
        raise NotImplementedError


@pytest.fixture
def signal() -> Signal:
    return Signal(
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=1,
        price=Decimal("70000"),
        reason="test signal",
    )


async def _create_account_with_risk_config(session: AsyncSession, **config_overrides) -> Account:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(account)
    await session.flush()

    defaults = dict(
        account_id=account.id,
        max_daily_loss_amount=Decimal("100000"),
        max_position_size=Decimal("1000000"),
        max_open_positions=5,
        max_trades_per_day=10,
        consecutive_loss_limit=3,
        emergency_stop=False,
    )
    defaults.update(config_overrides)
    session.add(RiskConfig(**defaults))
    await session.flush()

    return account


async def test_approved_signal_records_risk_event(db_session: AsyncSession, signal: Signal) -> None:
    account = await _create_account_with_risk_config(db_session)
    service = RiskService(db_session, FakeBrokerClient())

    result = await service.validate_signal(account.id, signal)

    assert result.approved is True

    events = (
        (await db_session.execute(select(RiskEvent).where(RiskEvent.account_id == account.id)))
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].result == RiskEventResult.APPROVED
    assert events[0].signal_snapshot["symbol_code"] == "005930"
    assert events[0].context_snapshot["account_balance"] == 10000000.0


async def test_rejected_signal_records_risk_event(db_session: AsyncSession, signal: Signal) -> None:
    account = await _create_account_with_risk_config(db_session, emergency_stop=True)
    service = RiskService(db_session, FakeBrokerClient())

    result = await service.validate_signal(account.id, signal)

    assert result.approved is False
    assert result.rule_name == "emergency_stop"

    events = (
        (await db_session.execute(select(RiskEvent).where(RiskEvent.account_id == account.id)))
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].result == RiskEventResult.REJECTED
    assert events[0].rule_name == "emergency_stop"


async def test_set_emergency_stop_updates_config_and_logs_event(db_session: AsyncSession) -> None:
    account = await _create_account_with_risk_config(db_session)
    service = RiskService(db_session, FakeBrokerClient())

    config = await service.set_emergency_stop(account.id, True)

    assert config.emergency_stop is True

    events = (
        (await db_session.execute(select(RiskEvent).where(RiskEvent.account_id == account.id)))
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].rule_name == "emergency_stop_toggle"
