"""RISK-FIX-1B — risk deadlock characterization tests.

이 파일은 **현재(flawed) 동작을 고정**하는 characterization test다. 모두 현재 코드 기준으로
PASS해야 한다. 기대값을 바꾸는 것은 다음 단계의 일이다:

  * RISK-FIX-1C — ConsecutiveLossLimitRule이 risk-reducing SELL/exit를 막지 않도록 변경
  * RISK-FIX-1D — MaxPositionSizeRule이 risk-reducing SELL/exit를 막지 않도록 변경
  * RISK-FIX-1E — fee-only break-even 청산을 연속 손실에서 제외

진단 근거: docs/diagnostics/no-trades-after-2026-06-26-risk-circuit-breaker.md
설계: docs/design/RISK-FIX-1-risk-reducing-exit-policy.md

순수 unit test — 실제 DB/broker/KIS/scheduler/주문 없음.
"""
from decimal import Decimal

import pytest

from app.domain.models.enums import TradeSide
from app.domain.models.risk import RiskConfig
from app.trading.risk.context import RiskContext, RiskContextBuilder
from app.trading.risk.manager import RiskManager
from app.trading.risk.rules import (
    DEFAULT_RULES,
    ConsecutiveLossLimitRule,
    MaxOpenPositionsRule,
    MaxPositionSizeRule,
)
from app.trading.strategy.base import Signal


# --- helpers (test_risk_rules.py 컨벤션과 동일) --------------------------------
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


# --- Test 1: ConsecutiveLossLimit이 SELL/exit까지 막는다 (현재 동작) -----------
def test_current_consecutive_loss_limit_blocks_sell_exit_characterization() -> None:
    # Characterization test for the current flawed behavior.
    # RISK-FIX-1C should change this expectation so risk-reducing exits are allowed.
    rule = ConsecutiveLossLimitRule()
    config = make_config(consecutive_loss_limit=3)
    context = make_context(
        consecutive_losses=5,  # 5 >= 3
        open_positions_count=6,
        current_position_value={"373220": Decimal("1468000")},
    )
    # 보유 중인 종목을 줄이는 손절 매도(risk-reducing exit).
    sell_exit = make_signal(
        symbol_code="373220", side=TradeSide.SELL, quantity=4, price=Decimal("367000"),
        reason="손절 (평가손익률 -1.94% <= -1.0%)",
    )

    result = rule.check(sell_exit, config, context)

    # 현재 코드는 side를 보지 않으므로 손절 매도까지 거부한다.
    assert result.approved is False
    assert result.rule_name == "consecutive_loss_limit"


# --- Test 2: MaxPositionSize가 SELL/exit까지 막는다 (현재 동작) ----------------
def test_current_max_position_size_blocks_sell_exit_characterization() -> None:
    # Characterization test for the current flawed behavior.
    # RISK-FIX-1D should change this expectation so risk-reducing exits are allowed.
    rule = MaxPositionSizeRule()
    config = make_config(max_position_size=Decimal("1000000"))
    context = make_context(
        open_positions_count=6,
        current_position_value={"373220": Decimal("1468000")},
    )
    # 주문금액 367,000 * 4 = 1,468,000 > 1,000,000 인 손절 매도.
    sell_exit = make_signal(
        symbol_code="373220", side=TradeSide.SELL, quantity=4, price=Decimal("367000"),
        reason="손절",
    )

    result = rule.check(sell_exit, config, context)

    # 현재 코드는 side를 보지 않고 order_amount만 비교하므로 손절 매도까지 거부한다.
    assert result.approved is False
    assert result.rule_name == "max_position_size"
    assert "1468000" in result.reason


# --- Test 3: MaxOpenPositions는 이미 SELL/exit를 막지 않는다 (entry-only) -------
def test_current_max_open_positions_does_not_block_sell_exit_characterization() -> None:
    # Characterization test: MaxOpenPositionsRule already behaves correctly here —
    # it only blocks NEW BUY entries, not risk-reducing SELL/exit.
    rule = MaxOpenPositionsRule()
    config = make_config(max_open_positions=5)
    context = make_context(
        open_positions_count=6,  # 6 >= 5 (한도 초과 상태)
        current_position_value={"373220": Decimal("1468000")},
    )
    # 보유 종목을 줄이는 매도는 보유 종목 수 한도와 무관해야 한다.
    sell_exit = make_signal(symbol_code="373220", side=TradeSide.SELL, quantity=4, price=Decimal("367000"))

    result = rule.check(sell_exit, config, context)

    assert result.approved is True

    # 대조군: 신규 BUY는 한도 초과 시 정상적으로 거부된다(현재도 올바른 동작).
    new_buy = make_signal(symbol_code="000270", side=TradeSide.BUY, quantity=1, price=Decimal("90000"))
    buy_result = rule.check(new_buy, config, context)
    assert buy_result.approved is False
    assert buy_result.rule_name == "max_open_positions"


# --- Test 4: 수수료성 break-even 청산이 연속 손실로 집계된다 (현재 동작) --------
class _FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return iter(self._values)


class _FakeSession:
    """_count_consecutive_losses가 사용하는 session.execute만 흉내내는 fake (DB 없음)."""

    def __init__(self, pnl_values):
        self._pnl_values = pnl_values

    async def execute(self, _stmt):
        return _FakeScalarResult(self._pnl_values)


async def test_current_fee_only_break_even_counts_as_consecutive_loss_characterization() -> None:
    # Characterization test for the current flawed behavior.
    # RISK-FIX-1E should exclude fee-only break-even round-trips from the loss streak.
    # 실제 데이터의 평탄 청산(entry_price == exit_price, pnl_pct == 0%)이지만
    # 수수료/세금 때문에 pnl_amount만 음수인 케이스.
    fee_only_losses = [Decimal("-907"), Decimal("-89"), Decimal("-49"), Decimal("-208"), Decimal("-220")]
    builder = RiskContextBuilder(session=_FakeSession(fee_only_losses), broker=None)

    count = await builder._count_consecutive_losses(account_id=230)

    # 현재 코드는 pnl_amount < 0 이면 무조건 손실로 세므로 5건 모두 연속 손실로 집계된다.
    assert count == 5

    # 대조: 첫 청산이 양수(이익)면 streak는 거기서 끊긴다.
    builder2 = RiskContextBuilder(
        session=_FakeSession([Decimal("100"), Decimal("-907"), Decimal("-89")]), broker=None
    )
    assert await builder2._count_consecutive_losses(account_id=230) == 0


# --- Test 5: 현재 규칙들이 exit deadlock을 만들 수 있다 (조합) ------------------
def test_current_rules_can_create_exit_deadlock_characterization() -> None:
    # Characterization test for the current flawed behavior.
    # RISK-FIX-1C/1D/1E should make risk-reducing exits pass so the deadlock breaks.
    manager = RiskManager(DEFAULT_RULES)
    config = make_config(
        consecutive_loss_limit=3, max_open_positions=5, max_position_size=Decimal("1000000")
    )
    # 06-26 이후 실제 계좌 상태를 재현: 연속 손실 5, 보유 6종목.
    context = make_context(
        consecutive_losses=5,
        open_positions_count=6,
        current_position_value={
            "005380": Decimal("1497000"),
            "373220": Decimal("1468000"),
            "145020": Decimal("1060000"),
        },
    )

    # (a) 고가 포지션 손절 매도 — max_position_size가 먼저 거부.
    high_notional_exit = make_signal(
        symbol_code="373220", side=TradeSide.SELL, quantity=4, price=Decimal("367000"))
    r_a = manager.validate(high_notional_exit, config, context)
    assert r_a.approved is False
    assert r_a.rule_name == "max_position_size"

    # (b) 소액 포지션 손절 매도 — 주문금액은 한도 내지만 consecutive_loss_limit이 거부.
    small_notional_exit = make_signal(
        symbol_code="017670", side=TradeSide.SELL, quantity=1, price=Decimal("89300"))
    r_b = manager.validate(small_notional_exit, config, context)
    assert r_b.approved is False
    assert r_b.rule_name == "consecutive_loss_limit"

    # (c) 신규 진입 매수 — 어차피 거부(연속 손실 한도).
    new_buy = make_signal(
        symbol_code="000270", side=TradeSide.BUY, quantity=1, price=Decimal("90000"))
    r_c = manager.validate(new_buy, config, context)
    assert r_c.approved is False

    # 결론: 현재 코드에서는 위험을 줄이는 어떤 청산도 통과하지 못하고 신규 진입도 막혀 데드락이 된다.
