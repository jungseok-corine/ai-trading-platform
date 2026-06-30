"""RISK-FIX-1C — ConsecutiveLossLimitRule allows risk-reducing SELL/exit.

RISK-FIX-1B가 기록한 "연속 손실 한도가 SELL/exit까지 막는다"는 동작을 RISK-FIX-1C가
의도적으로 바꾼다:

  * BUY(위험을 추가하는 진입)는 연속 손실 한도로 계속 차단된다.
  * SELL(현재 long-only 구조의 risk-reducing exit/청산/손절)은 한도와 무관하게 허용된다.

전제(문서·테스트에 명시): 현재 시스템은 long-only이며 별도 action field 없이 Signal.side만
있다. 전략의 SELL 신호는 데드크로스/손절 등 청산 의도이고 short open 경로는 없다. 만약 향후
SELL이 short open으로 쓰이는 구조가 생기면 이 전제를 재검토해야 한다.

남은 데드락: MaxPositionSizeRule은 아직 SELL/exit를 막는다(RISK-FIX-1D에서 해결).
fee-only break-even 손실 카운트도 그대로다(RISK-FIX-1E에서 해결).

순수 unit test — 실제 DB/broker/KIS/scheduler/주문 없음.
"""
from decimal import Decimal

from app.domain.models.enums import TradeSide
from app.domain.models.risk import RiskConfig
from app.trading.risk.context import RiskContext
from app.trading.risk.rules import ConsecutiveLossLimitRule, MaxPositionSizeRule
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


# --- Test 1: BUY는 한도 초과 시 여전히 차단된다 -------------------------------
def test_consecutive_loss_limit_still_blocks_buy_entries() -> None:
    rule = ConsecutiveLossLimitRule()
    config = make_config(consecutive_loss_limit=3)
    context = make_context(consecutive_losses=5)  # 5 >= 3

    new_buy = make_signal(side=TradeSide.BUY, quantity=1, price=Decimal("90000"))
    result = rule.check(new_buy, config, context)

    assert result.approved is False
    assert result.rule_name == "consecutive_loss_limit"


# --- Test 2: SELL/exit는 한도 초과여도 허용된다 (RISK-FIX-1C) ------------------
def test_consecutive_loss_limit_allows_sell_exit_after_loss_limit() -> None:
    rule = ConsecutiveLossLimitRule()
    config = make_config(consecutive_loss_limit=3)
    context = make_context(
        consecutive_losses=5,  # 5 >= 3
        open_positions_count=6,
        current_position_value={"373220": Decimal("1468000")},
    )
    # 보유 종목을 줄이는 손절 매도 — risk-reducing exit이므로 연속 손실 한도와 무관하게 허용.
    sell_exit = make_signal(
        symbol_code="373220", side=TradeSide.SELL, quantity=1, price=Decimal("89300"),
        reason="손절 (평가손익률 -1.94% <= -1.0%)",
    )

    result = rule.check(sell_exit, config, context)

    assert result.approved is True


# --- Test 3: CLL은 SELL을 허용하고, MPS는 RISK-FIX-1D에서 별도로 SELL을 허용하게 됐다 ----
def test_consecutive_loss_fix_scope_is_cll_only_mps_handled_in_1d() -> None:
    # RISK-FIX-1C의 범위는 CLL에 한정된다(MPS는 건드리지 않았다).
    # 이 테스트는 작성 당시 "MPS는 아직 SELL을 막는다"를 고정했으나, 그 후 RISK-FIX-1D가
    # MPS의 SELL 동작을 바꿔(고가 청산 허용) 남은 데드락을 제거했다 → 현재 코드 기준으로 갱신.
    config = make_config(consecutive_loss_limit=3, max_position_size=Decimal("1000000"))
    context = make_context(
        consecutive_losses=5,
        open_positions_count=6,
        current_position_value={"373220": Decimal("1468000")},
    )
    # 주문금액 367,000 * 4 = 1,468,000 > 1,000,000 인 손절 매도.
    sell_exit = make_signal(
        symbol_code="373220", side=TradeSide.SELL, quantity=4, price=Decimal("367000"))

    # CLL(RISK-FIX-1C): SELL 허용.
    cll_result = ConsecutiveLossLimitRule().check(sell_exit, config, context)
    assert cll_result.approved is True

    # MPS(RISK-FIX-1D): 이제 SELL 허용(과거에는 거부했음).
    mps_result = MaxPositionSizeRule().check(sell_exit, config, context)
    assert mps_result.approved is True
