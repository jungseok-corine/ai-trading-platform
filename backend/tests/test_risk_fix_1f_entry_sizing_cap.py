"""RISK-FIX-1F — entry quantity sizing cap (pure helper + rule-level).

BUY 진입 수량을 max_position_size 한도 내로 사전 cap한다. SELL/exit는 cap하지 않는다.
cap 결과 수량이 0이면 호출측(TradeService.execute_signal)이 no-trade로 처리한다
(서비스 레벨/브로커 미호출 검증은 test_trade_service.py 참고).

진행 맥락: 1C(CLL exit 허용) · 1D(MPS exit 허용) · 1E(fee-only 손실 제외) 이후 마지막 단계.
`MaxPositionSizeRule`은 cap을 우회한 BUY에 대한 defense-in-depth로 남는다.

순수 unit test — 실제 DB/broker/KIS/scheduler/주문 없음.
"""
from decimal import Decimal

from app.domain.models.enums import TradeSide
from app.domain.models.risk import RiskConfig
from app.trading.risk.context import RiskContext
from app.trading.risk.rules import (
    ConsecutiveLossLimitRule,
    MaxOpenPositionsRule,
    MaxPositionSizeRule,
)
from app.trading.risk.sizing import cap_buy_quantity_by_position_size
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


# --- Test 1: BUY 수량이 max_position_size로 cap된다 ---------------------------
def test_buy_quantity_is_capped_by_max_position_size() -> None:
    capped = cap_buy_quantity_by_position_size(
        side=TradeSide.BUY, price=Decimal("400000"), quantity=4,
        max_position_size=Decimal("1000000"))
    assert capped == 2  # floor(1,000,000 / 400,000) = 2
    assert Decimal("400000") * capped <= Decimal("1000000")


# --- Test 2: 한도 내면 수량 그대로 --------------------------------------------
def test_buy_quantity_unchanged_when_within_limit() -> None:
    capped = cap_buy_quantity_by_position_size(
        side=TradeSide.BUY, price=Decimal("100000"), quantity=5,
        max_position_size=Decimal("1000000"))
    assert capped == 5


# --- Test 3: cap 결과가 0이면 0 반환(호출측이 no-trade 처리) -------------------
def test_buy_capped_to_zero_when_price_exceeds_limit() -> None:
    capped = cap_buy_quantity_by_position_size(
        side=TradeSide.BUY, price=Decimal("1500000"), quantity=1,
        max_position_size=Decimal("1000000"))
    assert capped == 0  # floor(1,000,000 / 1,500,000) = 0


# --- Test 4: SELL 수량은 cap하지 않는다 ---------------------------------------
def test_sell_quantity_is_not_capped() -> None:
    capped = cap_buy_quantity_by_position_size(
        side=TradeSide.SELL, price=Decimal("500000"), quantity=4,
        max_position_size=Decimal("1000000"))
    assert capped == 4  # 2,000,000 > 1,000,000 이지만 SELL은 줄이지 않음


def test_invalid_inputs_do_not_cap_conservatively() -> None:
    # price <= 0 → cap 안 함(원래 수량). MaxPositionSizeRule이 방어선.
    assert cap_buy_quantity_by_position_size(
        side=TradeSide.BUY, price=Decimal("0"), quantity=3,
        max_position_size=Decimal("1000000")) == 3
    # max_position_size <= 0 → cap 안 함.
    assert cap_buy_quantity_by_position_size(
        side=TradeSide.BUY, price=Decimal("100000"), quantity=3,
        max_position_size=Decimal("0")) == 3


def test_us_fx_rate_is_applied_in_cap() -> None:
    # US 주문: price 100 USD * qty 200 * fx 1350 = 27,000,000 KRW. 한도 1,000,000 KRW.
    # max_allowed = floor(1,000,000 / (100 * 1350)) = floor(7.4) = 7.
    capped = cap_buy_quantity_by_position_size(
        side=TradeSide.BUY, price=Decimal("100"), quantity=200,
        max_position_size=Decimal("1000000"), fx_rate=Decimal("1350"))
    assert capped == 7


# --- Test 5: cap된 BUY는 MaxPositionSizeRule을 통과한다 ------------------------
def test_risk_manager_accepts_capped_buy() -> None:
    config = make_config(max_position_size=Decimal("1000000"))
    capped = cap_buy_quantity_by_position_size(
        side=TradeSide.BUY, price=Decimal("400000"), quantity=4,
        max_position_size=config.max_position_size)
    buy = make_signal(symbol_code="373220", side=TradeSide.BUY, quantity=capped, price=Decimal("400000"))

    result = MaxPositionSizeRule().check(buy, config, make_context())

    assert result.approved is True


# --- Test 6: cap을 우회한 BUY는 MaxPositionSizeRule이 여전히 막는다 (방어선) ----
def test_risk_manager_still_rejects_uncapped_buy_above_limit() -> None:
    config = make_config(max_position_size=Decimal("1000000"))
    # cap을 적용하지 않은 원래 수량 4 → 1,600,000 > 1,000,000.
    buy = make_signal(symbol_code="373220", side=TradeSide.BUY, quantity=4, price=Decimal("400000"))

    result = MaxPositionSizeRule().check(buy, config, make_context())

    assert result.approved is False
    assert result.rule_name == "max_position_size"


# --- Test 7: exit 정책(1C/1D)은 변하지 않는다 --------------------------------
def test_existing_exit_policy_remains_unchanged() -> None:
    config = make_config(consecutive_loss_limit=3, max_position_size=Decimal("1000000"),
                         max_open_positions=5)
    context = make_context(
        consecutive_losses=5, open_positions_count=6,
        current_position_value={"373220": Decimal("1468000")},
    )
    sell_exit = make_signal(
        symbol_code="373220", side=TradeSide.SELL, quantity=4, price=Decimal("367000"))

    assert ConsecutiveLossLimitRule().check(sell_exit, config, context).approved is True
    assert MaxPositionSizeRule().check(sell_exit, config, context).approved is True
    assert MaxOpenPositionsRule().check(sell_exit, config, context).approved is True
