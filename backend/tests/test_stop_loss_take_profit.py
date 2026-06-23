"""손절(stop_loss_pct) / 익절(take_profit_pct) 기능 테스트."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, StrategyVersionStatus
from app.domain.models.risk import RiskConfig
from app.domain.models.strategy import Strategy, StrategyVersion
from app.services.market_data_service import MarketDataService
from app.services.risk_service import RiskService
from app.services.signal_service import SignalService
from app.services.strategy_runner_service import StrategyRunnerService
from app.services.trade_service import TradeService
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
from app.domain.models.enums import TradeSide

KST = ZoneInfo("Asia/Seoul")

SYMBOL = "005930"
GOLDEN_CROSS_CLOSES = [100] * 20 + [200]


def _make_candles(closes: list[int]) -> list[MinuteCandle]:
    return [
        MinuteCandle(
            business_date="20260623",
            trade_time=f"{900 + i:04d}00",
            open_price=Decimal(c), high_price=Decimal(c),
            low_price=Decimal(c), close_price=Decimal(c), volume=1000,
        )
        for i, c in enumerate(closes)
    ]


class FakeBrokerWithHolding(BrokerClient):
    """특정 종목의 보유 포지션(평가손익률)을 시뮬레이션하는 브로커 스텁."""

    def __init__(
        self,
        candles: list[MinuteCandle],
        holding_pnl_rate: Decimal | None = None,
        holding_qty: int = 10,
        place_order_error: Exception | None = None,
    ) -> None:
        self._candles = candles
        self._holding_pnl_rate = holding_pnl_rate
        self._holding_qty = holding_qty
        self._place_order_error = place_order_error
        self.place_order_calls: list[OrderRequest] = []

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(self, symbol_code: str, **kwargs) -> list[MinuteCandle]:
        return self._candles

    async def get_account_balance(self) -> AccountBalance:
        holdings = []
        if self._holding_pnl_rate is not None:
            holdings = [
                AccountHolding(
                    symbol_code=SYMBOL,
                    symbol_name="삼성전자",
                    quantity=self._holding_qty,
                    avg_purchase_price=Decimal("100"),
                    current_price=Decimal("100") * (1 + self._holding_pnl_rate / 100),
                    evaluation_amount=Decimal("1000"),
                    profit_loss_amount=Decimal("0"),
                    profit_loss_rate=self._holding_pnl_rate,
                )
            ]
        return AccountBalance(
            holdings=holdings,
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
        if self._place_order_error is not None:
            raise self._place_order_error
        self.place_order_calls.append(order)
        return OrderResult(
            broker_order_id="0000000001",
            order_status=OrderStatus.PENDING,
            ordered_at=datetime.now(KST),
        )

    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
        raise NotImplementedError


# --- _check_sl_tp 순수 로직 ---------------------------------------------------

def test_check_sl_tp_stop_loss_triggered() -> None:
    holding = AccountHolding(
        symbol_code=SYMBOL, symbol_name="삼성전자", quantity=10,
        avg_purchase_price=Decimal("100"), current_price=Decimal("97.5"),
        evaluation_amount=Decimal("975"), profit_loss_amount=Decimal("-25"),
        profit_loss_rate=Decimal("-2.5"),
    )
    reason, qty = StrategyRunnerService._check_sl_tp(
        SYMBOL, {SYMBOL: holding}, stop_loss_pct=2.0, take_profit_pct=None
    )
    assert reason is not None and "손절" in reason
    assert qty == 10


def test_check_sl_tp_take_profit_triggered() -> None:
    holding = AccountHolding(
        symbol_code=SYMBOL, symbol_name="삼성전자", quantity=5,
        avg_purchase_price=Decimal("100"), current_price=Decimal("106"),
        evaluation_amount=Decimal("530"), profit_loss_amount=Decimal("30"),
        profit_loss_rate=Decimal("6.0"),
    )
    reason, qty = StrategyRunnerService._check_sl_tp(
        SYMBOL, {SYMBOL: holding}, stop_loss_pct=None, take_profit_pct=5.0
    )
    assert reason is not None and "익절" in reason
    assert qty == 5


def test_check_sl_tp_within_range_no_trigger() -> None:
    holding = AccountHolding(
        symbol_code=SYMBOL, symbol_name="삼성전자", quantity=10,
        avg_purchase_price=Decimal("100"), current_price=Decimal("99"),
        evaluation_amount=Decimal("990"), profit_loss_amount=Decimal("-10"),
        profit_loss_rate=Decimal("-1.0"),
    )
    reason, qty = StrategyRunnerService._check_sl_tp(
        SYMBOL, {SYMBOL: holding}, stop_loss_pct=2.0, take_profit_pct=5.0
    )
    assert reason is None
    assert qty is None


def test_check_sl_tp_no_holding_no_trigger() -> None:
    reason, qty = StrategyRunnerService._check_sl_tp(
        SYMBOL, {}, stop_loss_pct=2.0, take_profit_pct=5.0
    )
    assert reason is None


# --- 통합: 러너가 손절 신호를 생성하고 자동매매를 시도한다 -------------------

async def _setup_runner(
    session: AsyncSession,
    pnl_rate: Decimal,
    stop_loss_pct: float | None,
    take_profit_pct: float | None,
) -> tuple[StrategyRunnerService, FakeBrokerWithHolding, StrategyVersion, Account]:
    candles = _make_candles(GOLDEN_CROSS_CLOSES)
    broker = FakeBrokerWithHolding(candles, holding_pnl_rate=pnl_rate)

    account = Account(account_type=AccountType.PAPER, broker_account_no="sl-tp-test")
    session.add(account)
    await session.flush()
    session.add(RiskConfig(
        account_id=account.id,
        max_daily_loss_amount=Decimal("1000000"),
        max_position_size=Decimal("5000000"),
        max_open_positions=10,
        max_trades_per_day=100,
        consecutive_loss_limit=10,
        emergency_stop=False,
    ))

    strategy = Strategy(name="SL/TP Test", description="t")
    session.add(strategy)
    await session.flush()
    version = StrategyVersion(
        strategy_id=strategy.id, version_no=1, status=StrategyVersionStatus.ACTIVE,
        parameters={
            "strategy_type": "moving_average_cross",
            "symbol_code": SYMBOL,
            "short_window": 5, "long_window": 20,
            "quantity": 3,
            "auto_trade_enabled": True,
            "account_id": account.id,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "enabled": True,
        },
    )
    session.add(version)
    await session.commit()

    risk_svc = RiskService(session, broker)
    trade_svc = TradeService(session, broker, risk_service=risk_svc)
    signal_svc = SignalService(session, MarketDataService(broker))
    runner = StrategyRunnerService(session, signal_svc, trade_svc)
    return runner, broker, version, account


async def test_stop_loss_generates_sell_and_attempts_trade(db_session: AsyncSession) -> None:
    """평가손익률 -2.5%일 때 stop_loss_pct=2 → SELL 신호 생성 + 자동매매 시도."""
    runner, broker, version, _ = await _setup_runner(
        db_session, pnl_rate=Decimal("-2.5"), stop_loss_pct=2.0, take_profit_pct=None
    )
    now = datetime(2026, 6, 23, 10, 0, tzinfo=KST)
    results = await runner.run_once(now=now)

    assert len(results) == 1
    r = results[0]
    assert r.signal_created
    assert r.trade_attempted
    assert len(broker.place_order_calls) == 1
    order = broker.place_order_calls[0]
    assert order.side == TradeSide.SELL
    assert order.quantity == 10  # holding quantity, not strategy quantity=3


async def test_take_profit_generates_sell_and_attempts_trade(db_session: AsyncSession) -> None:
    """평가손익률 +6%일 때 take_profit_pct=5 → SELL 신호 생성 + 자동매매 시도."""
    runner, broker, version, _ = await _setup_runner(
        db_session, pnl_rate=Decimal("6.0"), stop_loss_pct=None, take_profit_pct=5.0
    )
    now = datetime(2026, 6, 23, 10, 0, tzinfo=KST)
    results = await runner.run_once(now=now)

    assert len(results) == 1
    r = results[0]
    assert r.signal_created
    assert r.trade_attempted
    order = broker.place_order_calls[0]
    assert order.side == TradeSide.SELL


async def test_within_range_no_forced_sell(db_session: AsyncSession) -> None:
    """평가손익률 -1%: stop_loss 2%, take_profit 5% → 강제 매도 없음, 일반 전략 신호 동작."""
    runner, broker, _, _ = await _setup_runner(
        db_session, pnl_rate=Decimal("-1.0"), stop_loss_pct=2.0, take_profit_pct=5.0
    )
    now = datetime(2026, 6, 23, 10, 0, tzinfo=KST)
    results = await runner.run_once(now=now)

    assert len(results) == 1
    # MA 골든크로스(BUY) 신호가 생성되므로 signal_created=True이지만,
    # 강제 SELL이 아닌 일반 BUY 신호 — 브로커 place_order가 호출됨
    r = results[0]
    assert r.signal_created
    if broker.place_order_calls:
        assert broker.place_order_calls[0].side == TradeSide.BUY
