from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, StrategyVersionStatus, TradeAttemptStatus
from app.domain.models.risk import RiskConfig, RiskEvent
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade
from app.services.market_data_service import MarketDataService
from app.services.risk_service import RiskService
from app.services.signal_service import SignalService
from app.services.strategy_runner_service import StrategyRunnerService, StrategyRunResult
from app.services.trade_service import TradeService
from app.trading.broker.base import BrokerClient
from app.trading.broker.error_classifier import KIS_ERROR_UNKNOWN
from app.trading.broker.exceptions import KISAPIError
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

KST = ZoneInfo("Asia/Seoul")

GOLDEN_CROSS_CLOSES = [100] * 20 + [200]


def _make_candles(closes: list[int]) -> list[MinuteCandle]:
    candles = []
    for i, close in enumerate(closes):
        price = Decimal(close)
        candles.append(
            MinuteCandle(
                business_date="20260610",
                trade_time=f"{900 + i:04d}00",
                open_price=price,
                high_price=price,
                low_price=price,
                close_price=price,
                volume=1000,
            )
        )
    return candles


class FakeBrokerClient(BrokerClient):
    """symbol_code별 분봉 데이터 + place_order 호출 기록/오류 시뮬레이션."""

    def __init__(
        self,
        candles_by_symbol: dict[str, list[MinuteCandle]],
        place_order_error: Exception | None = None,
    ) -> None:
        self._candles_by_symbol = candles_by_symbol
        self._place_order_error = place_order_error
        self.place_order_calls: list[OrderRequest] = []

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        return self._candles_by_symbol.get(symbol_code, [])

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


async def _create_strategy_version(
    session: AsyncSession, parameters: dict, status: StrategyVersionStatus = StrategyVersionStatus.ACTIVE
) -> StrategyVersion:
    strategy = Strategy(name="MA Cross Auto Trade Test", description="test")
    session.add(strategy)
    await session.flush()

    version = StrategyVersion(
        strategy_id=strategy.id,
        version_no=1,
        parameters=parameters,
        status=status,
    )
    session.add(version)
    await session.flush()
    return version


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


def _runner(session: AsyncSession, broker: BrokerClient) -> StrategyRunnerService:
    signal_service = SignalService(session, MarketDataService(broker))
    risk_service = RiskService(session, broker)
    trade_service = TradeService(session, broker, risk_service)
    return StrategyRunnerService(session, signal_service, trade_service)


def _params(**overrides) -> dict:
    base = {
        "strategy_type": "moving_average_cross",
        "symbol_code": "005930",
        "short_window": 5,
        "long_window": 20,
        "quantity": 1,
        "timeframe": "1m",
        "enabled": True,
        "auto_trade_enabled": False,
    }
    base.update(overrides)
    return base


async def test_auto_trade_disabled_only_saves_signal(db_session: AsyncSession) -> None:
    await _create_strategy_version(db_session, _params(auto_trade_enabled=False))
    broker = FakeBrokerClient({"005930": _make_candles(GOLDEN_CROSS_CLOSES)})

    results = await _runner(db_session, broker).run_once()

    assert len(results) == 1
    assert results[0].signal_created is True
    assert results[0].auto_trade_enabled is False
    assert results[0].trade_attempted is False

    assert broker.place_order_calls == []
    trades = (await db_session.execute(select(Trade))).scalars().all()
    assert trades == []


async def test_auto_trade_enabled_approved_calls_trade_service(db_session: AsyncSession) -> None:
    account = await _create_account_with_risk_config(db_session)
    await _create_strategy_version(
        db_session, _params(auto_trade_enabled=True, account_id=account.id)
    )
    broker = FakeBrokerClient({"005930": _make_candles(GOLDEN_CROSS_CLOSES)})

    results = await _runner(db_session, broker).run_once()

    assert len(results) == 1
    result = results[0]
    assert result.signal_created is True
    assert result.auto_trade_enabled is True
    assert result.trade_attempted is True
    assert result.trade_approved is True
    assert result.trade_id is not None
    assert result.error is None

    assert len(broker.place_order_calls) == 1
    placed = broker.place_order_calls[0]
    assert placed.symbol_code == "005930"
    assert placed.quantity == 1
    assert placed.price == Decimal("200")

    trades = (
        (await db_session.execute(select(Trade).where(Trade.account_id == account.id))).scalars().all()
    )
    assert len(trades) == 1
    assert trades[0].id == result.trade_id

    log = (await db_session.execute(select(SignalLog))).scalars().one()
    assert log.trade_attempt_status == TradeAttemptStatus.APPROVED
    assert log.trade_id == result.trade_id
    assert log.trade_attempted_at is not None


async def test_auto_trade_enabled_without_account_id_returns_error(db_session: AsyncSession) -> None:
    await _create_strategy_version(db_session, _params(auto_trade_enabled=True))
    broker = FakeBrokerClient({"005930": _make_candles(GOLDEN_CROSS_CLOSES)})

    results = await _runner(db_session, broker).run_once()

    assert len(results) == 1
    result = results[0]
    assert result.signal_created is True
    assert result.auto_trade_enabled is True
    assert result.trade_attempted is False
    assert result.error is not None

    assert broker.place_order_calls == []

    signals = (await db_session.execute(select(SignalLog))).scalars().all()
    assert len(signals) == 1
    trades = (await db_session.execute(select(Trade))).scalars().all()
    assert trades == []


async def test_auto_trade_rejected_by_risk_manager_does_not_save_trade(db_session: AsyncSession) -> None:
    account = await _create_account_with_risk_config(db_session, emergency_stop=True)
    await _create_strategy_version(
        db_session, _params(auto_trade_enabled=True, account_id=account.id)
    )
    broker = FakeBrokerClient({"005930": _make_candles(GOLDEN_CROSS_CLOSES)})

    results = await _runner(db_session, broker).run_once()

    assert len(results) == 1
    result = results[0]
    assert result.trade_attempted is True
    assert result.trade_approved is False
    assert result.trade_id is None
    assert result.rejection_reason is not None

    assert broker.place_order_calls == []

    trades = (await db_session.execute(select(Trade))).scalars().all()
    assert trades == []

    risk_events = (
        (await db_session.execute(select(RiskEvent).where(RiskEvent.account_id == account.id)))
        .scalars()
        .all()
    )
    assert len(risk_events) == 1
    assert risk_events[0].rule_name == "emergency_stop"


async def test_auto_trade_kis_order_error_is_captured_as_error(db_session: AsyncSession) -> None:
    account = await _create_account_with_risk_config(db_session)
    await _create_strategy_version(
        db_session, _params(auto_trade_enabled=True, account_id=account.id)
    )
    broker = FakeBrokerClient(
        {"005930": _make_candles(GOLDEN_CROSS_CLOSES)},
        place_order_error=KISAPIError("1", "주문 실패"),
    )

    results = await _runner(db_session, broker).run_once()

    assert len(results) == 1
    result = results[0]
    assert result.signal_created is True
    assert result.trade_attempted is True
    assert result.trade_approved is None
    assert result.error is not None
    assert result.error_category == KIS_ERROR_UNKNOWN

    trades = (await db_session.execute(select(Trade))).scalars().all()
    assert trades == []

    log = (await db_session.execute(select(SignalLog))).scalars().one()
    assert log.trade_attempt_status == TradeAttemptStatus.ERROR


async def test_duplicate_trade_attempt_is_not_repeated(db_session: AsyncSession) -> None:
    """동일 signal_log에 대해 _attempt_auto_trade가 다시 호출되어도 추가 주문을 시도하지 않는다."""
    account = await _create_account_with_risk_config(db_session)
    version = await _create_strategy_version(
        db_session, _params(auto_trade_enabled=True, account_id=account.id)
    )
    broker = FakeBrokerClient({"005930": _make_candles(GOLDEN_CROSS_CLOSES)})
    runner = _runner(db_session, broker)

    results = await runner.run_once()
    assert results[0].trade_attempted is True
    assert results[0].trade_approved is True

    log = (await db_session.execute(select(SignalLog))).scalars().one()
    assert log.trade_attempt_status == TradeAttemptStatus.APPROVED
    assert len(broker.place_order_calls) == 1

    repeat_result = StrategyRunResult(
        strategy_version_id=version.id,
        symbol_code="005930",
        signal_created=True,
        signal_id=log.id,
        auto_trade_enabled=True,
        trade_attempted=False,
    )
    await runner._attempt_auto_trade(version, version.parameters, log, repeat_result)

    assert repeat_result.trade_attempted is False
    assert repeat_result.error is not None
    assert len(broker.place_order_calls) == 1

    trades = (await db_session.execute(select(Trade))).scalars().all()
    assert len(trades) == 1
