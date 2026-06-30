"""RISK-FIX-1B — risk deadlock characterization tests.

이 파일은 **남아 있는(아직 고치지 않은) 현재 동작을 고정**하는 characterization test다.
모두 현재 코드 기준으로 PASS해야 한다.

진행 상황:
  * RISK-FIX-1C (적용됨) — ConsecutiveLossLimitRule이 risk-reducing SELL/exit를 더 이상 막지 않는다.
    → 1B가 기록하던 "CLL이 SELL을 막는다" 기대는 더 이상 유효하지 않으며, 새 동작은
      test_risk_fix_1c_consecutive_loss_exit.py 로 이동했다(삭제가 아니라 의미 이전).
  * RISK-FIX-1D (미적용) — MaxPositionSizeRule이 여전히 SELL/exit를 막는다(아래 Test 2/5에서 고정).
  * RISK-FIX-1E (미적용) — fee-only break-even 청산이 여전히 연속 손실로 집계된다(아래 Test 4).

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


# NOTE: RISK-FIX-1B의 원래 Test 1
# (test_current_consecutive_loss_limit_blocks_sell_exit_characterization)은
# RISK-FIX-1C가 동작을 바꿨기 때문에 더 이상 유효하지 않다. 단순 삭제가 아니라,
# 새 기대(SELL 허용 / BUY 차단 유지)는 test_risk_fix_1c_consecutive_loss_exit.py 로 옮겼다.


# --- Test 2: MaxPositionSize가 SELL/exit까지 막는다 (현재 동작, RISK-FIX-1D 미적용) ---
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


# --- Test 5: RISK-FIX-1C 이후 데드락이 부분적으로만 줄었다 (조합) ----------------
def test_risk_fix_1c_removes_consecutive_loss_exit_block_but_mps_deadlock_remains() -> None:
    # RISK-FIX-1B captured the original full deadlock (CLL + MPS 모두 SELL을 막음).
    # RISK-FIX-1C intentionally changed CLL so risk-reducing SELL/exit는 통과한다.
    # 그러나 MaxPositionSizeRule은 아직 SELL을 막으므로(RISK-FIX-1D 필요) 고가 포지션 청산은 여전히 막힌다.
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

    # (a) 고가 포지션 손절 매도 — CLL은 이제 허용하지만 max_position_size가 여전히 거부(남은 데드락).
    high_notional_exit = make_signal(
        symbol_code="373220", side=TradeSide.SELL, quantity=4, price=Decimal("367000"))
    r_a = manager.validate(high_notional_exit, config, context)
    assert r_a.approved is False
    assert r_a.rule_name == "max_position_size"  # CLL이 아니라 MPS가 막는다 → RISK-FIX-1D 필요

    # (b) 소액 포지션 손절 매도 — 주문금액 한도 내. RISK-FIX-1C 이후 이제 통과한다(데드락 부분 해소).
    small_notional_exit = make_signal(
        symbol_code="017670", side=TradeSide.SELL, quantity=1, price=Decimal("89300"))
    r_b = manager.validate(small_notional_exit, config, context)
    assert r_b.approved is True

    # (c) 위험을 추가하는 매수 — 여전히 연속 손실 한도로 거부(의도된 차단 유지).
    #     (보유 종목 추가매수라 max_open_positions는 통과하고 CLL이 막는 경우로 구성.)
    add_buy = make_signal(
        symbol_code="373220", side=TradeSide.BUY, quantity=1, price=Decimal("90000"))
    r_c = manager.validate(add_buy, config, context)
    assert r_c.approved is False
    assert r_c.rule_name == "consecutive_loss_limit"

    # 결론: RISK-FIX-1C로 소액 청산은 가능해졌으나, 고가 포지션 청산을 막는 MaxPositionSizeRule
    # 데드락은 남아 있어 RISK-FIX-1D가 필요하다.
