"""RISK-FIX-1E — exclude fee-only break-even exits from the consecutive loss streak.

진행 맥락:
  * RISK-FIX-1B captured the old behavior (pnl_amount<0이면 무조건 연속 손실로 카운트).
  * RISK-FIX-1E (이 파일) intentionally changes fee-only break-even loss counting:
    수수료/세금만으로 pnl_amount<0인 평탄 청산(entry==exit, 방향 손익률≈0)은 streak에서 제외한다.
  * real directional losses(가격이 불리하게 움직인 청산)는 계속 손실로 카운트한다.
  * RISK-FIX-1F is still needed for entry sizing cap.

판정 기준(`_is_directional_streak_loss`):
  * 1순위: pnl_pct(=(exit-entry)/entry*100, percent point, 수수료 미포함).
  * pnl_pct 없으면 entry/exit price로 방향 손익률 계산.
  * directional_return_pct < -epsilon → 손실. |directional| <= epsilon → break-even(손실 아님).
  * 방향 데이터가 전혀 없으면 보수적으로 pnl_amount<0 으로 fallback.

CLL/MPS/MaxOpenPositions의 BUY/SELL 정책은 이 단계에서 바뀌지 않는다(1C/1D 그대로).

순수 unit test — 실제 DB/broker/KIS/scheduler/주문 없음.
"""
from decimal import Decimal

from app.domain.models.enums import TradeSide
from app.domain.models.risk import RiskConfig
from app.trading.risk.context import (
    CONSECUTIVE_LOSS_BREAK_EVEN_EPSILON_PCT,
    RiskContext,
    RiskContextBuilder,
    _is_directional_streak_loss,
)
from app.trading.risk.rules import (
    ConsecutiveLossLimitRule,
    MaxOpenPositionsRule,
    MaxPositionSizeRule,
)
from app.trading.strategy.base import Signal


# --- fakes / helpers ----------------------------------------------------------
class _FakeAllResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    """_count_consecutive_losses가 사용하는 session.execute만 흉내내는 fake (DB 없음).

    rows는 (pnl_amount, pnl_pct, entry_price, exit_price) 튜플의 리스트(최근 청산 순).
    """

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeAllResult(self._rows)


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


# row helpers (pnl_amount, pnl_pct, entry_price, exit_price)
def _fee_only_break_even(pnl_amount="-907", price="465000"):
    # entry == exit, pnl_pct == 0 이지만 수수료로 pnl_amount만 음수.
    return (Decimal(pnl_amount), Decimal("0.0000"), Decimal(price), Decimal(price))


def _real_directional_loss(entry="465000", exit_="460000", pnl_pct="-1.0753", pnl_amount="-5000"):
    return (Decimal(pnl_amount), Decimal(pnl_pct), Decimal(entry), Decimal(exit_))


# --- Test 1: fee-only break-even은 더 이상 연속 손실로 세지 않는다 --------------
async def test_fee_only_break_even_exit_does_not_count_as_consecutive_loss() -> None:
    rows = [_fee_only_break_even("-907"), _fee_only_break_even("-89"),
            _fee_only_break_even("-49"), _fee_only_break_even("-208"), _fee_only_break_even("-220")]
    builder = RiskContextBuilder(session=_FakeSession(rows), broker=None)

    assert await builder._count_consecutive_losses(account_id=230) == 0

    # 직접 판정도 확인.
    assert _is_directional_streak_loss(Decimal("-907"), Decimal("0.0000"),
                                       Decimal("465000"), Decimal("465000")) is False


# --- Test 2: 실제 가격 방향 손실은 계속 카운트된다 ----------------------------
async def test_real_directional_loss_still_counts_as_consecutive_loss() -> None:
    rows = [_real_directional_loss(), _real_directional_loss(), _real_directional_loss()]
    builder = RiskContextBuilder(session=_FakeSession(rows), broker=None)

    assert await builder._count_consecutive_losses(account_id=230) == 3

    assert _is_directional_streak_loss(Decimal("-5000"), Decimal("-1.94"),
                                       Decimal("465000"), Decimal("456000")) is True


# --- Test 3: epsilon 이내의 near-flat 움직임은 손실로 세지 않는다 --------------
def test_near_flat_directional_move_within_epsilon_does_not_count_as_loss() -> None:
    # 방향 손익률이 -epsilon 이내(절대값 epsilon 이하)면 break-even으로 보고 손실 아님.
    within = -(CONSECUTIVE_LOSS_BREAK_EVEN_EPSILON_PCT / 2)  # 예: -0.005
    assert _is_directional_streak_loss(Decimal("-50"), within,
                                       Decimal("465000"), Decimal("464980")) is False
    # 살짝 양수(수수료로 pnl_amount만 음수)인 경우도 손실 아님.
    assert _is_directional_streak_loss(Decimal("-10"), Decimal("0.0215"),
                                       Decimal("465000"), Decimal("465100")) is False


# --- Test 4: 방향 데이터가 없으면 보수적으로 pnl_amount로 fallback ------------
def test_missing_directional_data_falls_back_to_pnl_amount_conservatively() -> None:
    # pnl_pct/entry/exit가 모두 없으면 pnl_amount<0 → 손실.
    assert _is_directional_streak_loss(Decimal("-5000"), None, None, None) is True
    # pnl_amount도 없으면 손실 아님.
    assert _is_directional_streak_loss(None, None, None, None) is False
    # pnl_pct는 없지만 entry/exit가 있으면 방향 계산으로 판단(가격 하락 → 손실).
    assert _is_directional_streak_loss(Decimal("-5000"), None,
                                       Decimal("465000"), Decimal("460000")) is True


# --- Test 5: 실제 방향 손실이 한도 이상이면 CLL이 BUY를 계속 차단한다 ----------
async def test_consecutive_loss_limit_still_blocks_buy_after_real_directional_losses() -> None:
    rows = [_real_directional_loss(), _real_directional_loss(), _real_directional_loss()]
    builder = RiskContextBuilder(session=_FakeSession(rows), broker=None)
    count = await builder._count_consecutive_losses(account_id=230)
    assert count == 3

    config = make_config(consecutive_loss_limit=3)
    context = make_context(consecutive_losses=count)
    buy = make_signal(side=TradeSide.BUY, quantity=1, price=Decimal("90000"))
    assert ConsecutiveLossLimitRule().check(buy, config, context).approved is False


# --- Test 6: fee-only 손실만으로는 CLL이 트립되지 않는다 -----------------------
async def test_fee_only_break_even_losses_do_not_trip_consecutive_loss_limit() -> None:
    rows = [_fee_only_break_even(), _fee_only_break_even(), _fee_only_break_even(),
            _fee_only_break_even(), _fee_only_break_even()]
    builder = RiskContextBuilder(session=_FakeSession(rows), broker=None)
    count = await builder._count_consecutive_losses(account_id=230)
    assert count == 0  # 실제 방향 손실 0건

    config = make_config(consecutive_loss_limit=3)
    context = make_context(consecutive_losses=count)
    buy = make_signal(side=TradeSide.BUY, quantity=1, price=Decimal("90000"))
    # fee-only break-even만으로는 연속 손실 한도가 트립되지 않아 BUY가 통과한다.
    assert ConsecutiveLossLimitRule().check(buy, config, context).approved is True


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

    assert ConsecutiveLossLimitRule().check(sell_exit, config, context).approved is True  # CLL allows SELL
    assert MaxPositionSizeRule().check(sell_exit, config, context).approved is True        # MPS allows SELL
    assert MaxOpenPositionsRule().check(sell_exit, config, context).approved is True       # MOP allows SELL
