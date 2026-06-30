"""RISK-FIX-1B — risk deadlock characterization tests.

이 파일은 **남아 있는(아직 고치지 않은) 현재 동작을 고정**하는 characterization test다.
모두 현재 코드 기준으로 PASS해야 한다.

진행 상황:
  * RISK-FIX-1C (적용됨) — ConsecutiveLossLimitRule이 risk-reducing SELL/exit를 더 이상 막지 않는다.
    → 1B가 기록하던 "CLL이 SELL을 막는다" 기대는 더 이상 유효하지 않으며, 새 동작은
      test_risk_fix_1c_consecutive_loss_exit.py 로 이동했다(삭제가 아니라 의미 이전).
  * RISK-FIX-1D (적용됨) — MaxPositionSizeRule이 risk-reducing SELL/exit를 더 이상 막지 않는다.
    → 1B가 기록하던 "MPS가 SELL을 막는다"와 "CLL+MPS exit 데드락" 기대는 더 이상 유효하지 않으며,
      새 동작은 test_risk_fix_1d_max_position_size_exit.py 로 이동했다(삭제가 아니라 의미 이전).
  * RISK-FIX-1E (적용됨) — fee-only break-even 청산은 더 이상 연속 손실로 집계되지 않는다.
    → 1B가 기록하던 "fee-only break-even counts as loss" 기대는 더 이상 유효하지 않으며, 새 동작은
      test_risk_fix_1e_consecutive_loss_fee_only.py 로 이동했다(삭제가 아니라 의미 이전).

남아서 여전히 현재 동작을 고정하는 테스트: Test 3(MaxOpenPositions entry-only).

진단 근거: docs/diagnostics/no-trades-after-2026-06-26-risk-circuit-breaker.md
설계: docs/design/RISK-FIX-1-risk-reducing-exit-policy.md

순수 unit test — 실제 DB/broker/KIS/scheduler/주문 없음.
"""
from decimal import Decimal

from app.domain.models.enums import TradeSide
from app.domain.models.risk import RiskConfig
from app.trading.risk.context import RiskContext
from app.trading.risk.rules import MaxOpenPositionsRule
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


# NOTE: RISK-FIX-1B의 원래 Test 2
# (test_current_max_position_size_blocks_sell_exit_characterization)은
# RISK-FIX-1D가 동작을 바꿨기 때문에 더 이상 유효하지 않다. 단순 삭제가 아니라,
# 새 기대(SELL 허용 / BUY 차단 유지)는 test_risk_fix_1d_max_position_size_exit.py 로 옮겼다.


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


# NOTE: RISK-FIX-1B의 원래 Test 4
# (test_current_fee_only_break_even_counts_as_consecutive_loss_characterization)은
# RISK-FIX-1E가 동작을 바꿨기 때문에 더 이상 유효하지 않다. 단순 삭제가 아니라,
# 새 기대(fee-only break-even은 손실로 세지 않음 / real directional loss는 셈)는
# test_risk_fix_1e_consecutive_loss_fee_only.py 로 옮겼다.


# NOTE: RISK-FIX-1B의 원래 deadlock-chain 테스트(부분 해소 단계)는 RISK-FIX-1D 적용 후
# 더 이상 유효하지 않다(이제 고가 포지션 SELL도 통과). 업데이트된 "데드락 제거" 테스트는
# test_risk_fix_1d_max_position_size_exit.py 의
# test_risk_fix_1d_removes_cll_and_mps_exit_deadlock 로 옮겼다(삭제가 아니라 의미 이전).
