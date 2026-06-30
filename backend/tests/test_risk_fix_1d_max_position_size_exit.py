"""RISK-FIX-1D — MaxPositionSizeRule allows risk-reducing SELL/exit.

진행 맥락:
  * RISK-FIX-1B captured the original behavior (CLL + MPS 모두 SELL/exit를 막아 데드락).
  * RISK-FIX-1C changed CLL — risk-reducing SELL/exit는 연속 손실 한도로 막히지 않는다.
  * RISK-FIX-1D (이 파일) intentionally changes MPS — risk-reducing SELL/exit는 주문 금액 한도로
    막히지 않는다. 두 변경으로 DIAG-2에서 확인된 "risk rules가 손절 SELL 자체를 막는 데드락"이 해소된다.
  * RISK-FIX-1E is still needed for fee-only break-even loss counting.
  * RISK-FIX-1F is still needed for entry sizing cap.

정책:
  * BUY(위험을 추가하는 진입)는 `price * quantity > max_position_size`이면 계속 차단된다.
  * SELL(long-only 구조의 risk-reducing exit/청산/손절)은 주문 금액이 한도를 넘어도 허용된다.
  * SELL 허용은 주문 실행을 뜻하지 않는다 — risk rule이 막지 않는다는 뜻이며, 실제 주문/체결은
    별도 trade/order path의 책임이다.

전제(문서·테스트에 명시): 현재 시스템은 long-only이며 Signal.side만 있다(별도 action field 없음).
전략의 SELL은 청산 의도이고 short open 경로는 없다. 향후 SELL이 short open으로 쓰이면 전제를 재검토한다.

순수 unit test — 실제 DB/broker/KIS/scheduler/주문 없음.
"""
from decimal import Decimal

from app.domain.models.enums import TradeSide
from app.domain.models.risk import RiskConfig
from app.trading.risk.context import RiskContext
from app.trading.risk.manager import RiskManager
from app.trading.risk.rules import (
    DEFAULT_RULES,
    ConsecutiveLossLimitRule,
    MaxOpenPositionsRule,
    MaxPositionSizeRule,
)
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


# --- Test 1: MaxPositionSize는 BUY 진입을 한도 초과 시 여전히 차단한다 ----------
def test_max_position_size_still_blocks_buy_entries_above_limit() -> None:
    rule = MaxPositionSizeRule()
    config = make_config(max_position_size=Decimal("1000000"))
    # 주문금액 367,000 * 4 = 1,468,000 > 1,000,000 인 신규 매수.
    buy = make_signal(symbol_code="373220", side=TradeSide.BUY, quantity=4, price=Decimal("367000"))

    result = rule.check(buy, config, make_context())

    assert result.approved is False
    assert result.rule_name == "max_position_size"
    assert "1468000" in result.reason


# --- Test 2: MaxPositionSize는 SELL/exit를 한도 초과여도 허용한다 (RISK-FIX-1D) -
def test_max_position_size_allows_sell_exit_above_limit() -> None:
    rule = MaxPositionSizeRule()
    config = make_config(max_position_size=Decimal("1000000"))
    context = make_context(
        open_positions_count=6,
        current_position_value={"373220": Decimal("1468000")},
    )
    # 주문금액 367,000 * 4 = 1,468,000 > 1,000,000 인 손절 매도(risk-reducing exit).
    sell_exit = make_signal(
        symbol_code="373220", side=TradeSide.SELL, quantity=4, price=Decimal("367000"),
        reason="손절 (평가손익률 -1.94% <= -1.0%)",
    )

    result = rule.check(sell_exit, config, context)

    assert result.approved is True


# --- Test 3: ConsecutiveLossLimit 동작은 1C 그대로 유지된다 --------------------
def test_risk_fix_1d_does_not_change_consecutive_loss_behavior() -> None:
    rule = ConsecutiveLossLimitRule()
    config = make_config(consecutive_loss_limit=3)
    context = make_context(consecutive_losses=5)

    # BUY는 여전히 차단.
    buy = make_signal(side=TradeSide.BUY, quantity=1, price=Decimal("90000"))
    assert rule.check(buy, config, context).approved is False

    # SELL은 여전히 허용.
    sell = make_signal(symbol_code="373220", side=TradeSide.SELL, quantity=1, price=Decimal("89300"))
    assert rule.check(sell, config, context).approved is True


# --- Test 4: MaxOpenPositions 동작은 변하지 않는다 ----------------------------
def test_risk_fix_1d_max_open_positions_behavior_unchanged() -> None:
    rule = MaxOpenPositionsRule()
    config = make_config(max_open_positions=5)
    context = make_context(
        open_positions_count=6,
        current_position_value={"373220": Decimal("1468000")},
    )
    # 신규 BUY는 한도 초과로 차단.
    new_buy = make_signal(symbol_code="000270", side=TradeSide.BUY, quantity=1, price=Decimal("90000"))
    assert rule.check(new_buy, config, context).rule_name == "max_open_positions"
    # SELL/exit는 막지 않음.
    sell_exit = make_signal(symbol_code="373220", side=TradeSide.SELL, quantity=4, price=Decimal("367000"))
    assert rule.check(sell_exit, config, context).approved is True


# --- Test 6: CLL + MPS exit 데드락이 제거되었다 (조합) ------------------------
def test_risk_fix_1d_removes_cll_and_mps_exit_deadlock() -> None:
    # DIAG-2에서 확인된 "risk rules가 손절 SELL 자체를 막는 데드락"이 1C+1D로 해소됨을 검증한다.
    manager = RiskManager(DEFAULT_RULES)
    config = make_config(
        consecutive_loss_limit=3, max_open_positions=5, max_position_size=Decimal("1000000")
    )
    # 06-26 이후 실제 계좌 상태를 재현: 연속 손실 5, 보유 6종목, 고가 포지션 다수.
    context = make_context(
        consecutive_losses=5,
        open_positions_count=6,
        current_position_value={
            "005380": Decimal("1497000"),
            "373220": Decimal("1468000"),
            "145020": Decimal("1060000"),
        },
    )

    # 고가 포지션 손절 매도 — 이제 CLL/MPS/MaxOpenPositions 모두 통과한다.
    high_notional_exit = make_signal(
        symbol_code="373220", side=TradeSide.SELL, quantity=4, price=Decimal("367000"))
    assert manager.validate(high_notional_exit, config, context).approved is True

    # 소액 포지션 손절 매도 — 역시 통과.
    small_notional_exit = make_signal(
        symbol_code="017670", side=TradeSide.SELL, quantity=1, price=Decimal("89300"))
    assert manager.validate(small_notional_exit, config, context).approved is True


# --- Test 7: BUY 위험 보호는 그대로 유지된다 ---------------------------------
def test_buy_risk_protection_remains_intact_after_exit_fixes() -> None:
    manager = RiskManager(DEFAULT_RULES)

    # (a) 연속 손실 한도 — BUY 차단(보유 종목 추가매수라 max_open_positions는 통과).
    cfg_cll = make_config(consecutive_loss_limit=3, max_open_positions=5)
    ctx_cll = make_context(
        consecutive_losses=5, open_positions_count=1,
        current_position_value={"005930": Decimal("700000")},
    )
    add_buy = make_signal(symbol_code="005930", side=TradeSide.BUY, quantity=1, price=Decimal("70000"))
    r_cll = manager.validate(add_buy, cfg_cll, ctx_cll)
    assert r_cll.approved is False
    assert r_cll.rule_name == "consecutive_loss_limit"

    # (b) 주문 금액 한도 — BUY 차단.
    cfg_mps = make_config(max_position_size=Decimal("1000000"))
    big_buy = make_signal(symbol_code="373220", side=TradeSide.BUY, quantity=4, price=Decimal("367000"))
    r_mps = manager.validate(big_buy, cfg_mps, make_context())
    assert r_mps.approved is False
    assert r_mps.rule_name == "max_position_size"

    # (c) 보유 종목 수 한도 — 신규 BUY 차단.
    cfg_mop = make_config(max_open_positions=5)
    ctx_mop = make_context(open_positions_count=6, current_position_value={"373220": Decimal("1468000")})
    new_buy = make_signal(symbol_code="000270", side=TradeSide.BUY, quantity=1, price=Decimal("90000"))
    r_mop = manager.validate(new_buy, cfg_mop, ctx_mop)
    assert r_mop.approved is False
    assert r_mop.rule_name == "max_open_positions"
