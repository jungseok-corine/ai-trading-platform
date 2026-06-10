from decimal import Decimal

import pytest

from app.domain.models.enums import TradeSide
from app.domain.models.risk import RiskConfig
from app.trading.risk.context import RiskContext
from app.trading.risk.manager import RiskManager
from app.trading.risk.rules import DEFAULT_RULES, RiskCheckResult
from app.trading.strategy.base import Signal


def make_config(**overrides) -> RiskConfig:
    defaults = dict(
        account_id=1,
        max_daily_loss_amount=Decimal("100000"),
        max_position_size=Decimal("1000000"),
        max_open_positions=5,
        max_trades_per_day=10,
        consecutive_loss_limit=3,
        emergency_stop=False,
    )
    defaults.update(overrides)
    return RiskConfig(**defaults)


def make_context(**overrides) -> RiskContext:
    defaults = dict(
        account_id=1,
        account_balance=Decimal("10000000"),
        today_realized_pnl=Decimal("0"),
        today_trade_count=0,
        open_positions_count=0,
        consecutive_losses=0,
        current_position_value={},
    )
    defaults.update(overrides)
    return RiskContext(**defaults)


def make_signal(**overrides) -> Signal:
    defaults = dict(
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
        reason="test signal",
        strategy_version_id=None,
    )
    defaults.update(overrides)
    return Signal(**defaults)


@pytest.fixture
def manager() -> RiskManager:
    return RiskManager(DEFAULT_RULES)


def test_emergency_stop_rejects_all(manager: RiskManager) -> None:
    config = make_config(emergency_stop=True)
    result = manager.validate(make_signal(), config, make_context())

    assert result.approved is False
    assert result.rule_name == "emergency_stop"


def test_max_daily_loss_rejects(manager: RiskManager) -> None:
    config = make_config(max_daily_loss_amount=Decimal("50000"))
    context = make_context(today_realized_pnl=Decimal("-50000"))

    result = manager.validate(make_signal(), config, context)

    assert result.approved is False
    assert result.rule_name == "max_daily_loss"


def test_max_position_size_rejects(manager: RiskManager) -> None:
    config = make_config(max_position_size=Decimal("500000"))
    signal = make_signal(price=Decimal("70000"), quantity=10)  # 700,000 > 500,000

    result = manager.validate(signal, config, make_context())

    assert result.approved is False
    assert result.rule_name == "max_position_size"


def test_max_open_positions_rejects_new_symbol(manager: RiskManager) -> None:
    config = make_config(max_open_positions=2)
    context = make_context(
        open_positions_count=2,
        current_position_value={"000660": Decimal("1000000")},
    )
    signal = make_signal(symbol_code="005930", side=TradeSide.BUY)

    result = manager.validate(signal, config, context)

    assert result.approved is False
    assert result.rule_name == "max_open_positions"


def test_max_open_positions_allows_existing_symbol(manager: RiskManager) -> None:
    config = make_config(max_open_positions=1)
    context = make_context(
        open_positions_count=1,
        current_position_value={"005930": Decimal("700000")},
    )
    signal = make_signal(symbol_code="005930", side=TradeSide.BUY)

    result = manager.validate(signal, config, context)

    assert result.approved is True


def test_max_trades_per_day_rejects(manager: RiskManager) -> None:
    config = make_config(max_trades_per_day=5)
    context = make_context(today_trade_count=5)

    result = manager.validate(make_signal(), config, context)

    assert result.approved is False
    assert result.rule_name == "max_trades_per_day"


def test_consecutive_loss_limit_rejects(manager: RiskManager) -> None:
    config = make_config(consecutive_loss_limit=3)
    context = make_context(consecutive_losses=3)

    result = manager.validate(make_signal(), config, context)

    assert result.approved is False
    assert result.rule_name == "consecutive_loss_limit"


def test_all_rules_pass_returns_approved(manager: RiskManager) -> None:
    result = manager.validate(make_signal(), make_config(), make_context())

    assert result == RiskCheckResult(approved=True)
