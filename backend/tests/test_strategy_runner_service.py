from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.services.market_data_service import MarketDataService
from app.services.signal_service import SignalService
from app.services.strategy_runner_service import StrategyRunnerService
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
    """symbol_code별로 고정된 분봉 데이터를 반환한다."""

    def __init__(
        self,
        candles_by_symbol: dict[str, list[MinuteCandle]] | None = None,
        candles_error_by_symbol: dict[str, Exception] | None = None,
    ) -> None:
        self._candles_by_symbol = candles_by_symbol or {}
        self._candles_error_by_symbol = candles_error_by_symbol or {}

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        if symbol_code in self._candles_error_by_symbol:
            raise self._candles_error_by_symbol[symbol_code]
        return self._candles_by_symbol.get(symbol_code, [])

    async def get_account_balance(self) -> AccountBalance:
        return AccountBalance(
            holdings=[],
            summary=AccountSummary(
                total_deposit=Decimal("0"),
                total_purchase_amount=Decimal("0"),
                total_evaluation_amount=Decimal("0"),
                total_profit_loss_amount=Decimal("0"),
            ),
        )

    async def get_account_positions(self) -> list[AccountHolding]:
        return []

    async def place_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def get_daily_executions(self, start_date: str | None = None, end_date: str | None = None) -> list[OrderExecution]:
        raise NotImplementedError


async def _create_strategy_version(
    session: AsyncSession, parameters: dict, status: StrategyVersionStatus = StrategyVersionStatus.ACTIVE
) -> StrategyVersion:
    strategy = Strategy(name="MA Cross Test", description="test")
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


def _runner(session: AsyncSession, broker: BrokerClient) -> StrategyRunnerService:
    return StrategyRunnerService(session, SignalService(session, MarketDataService(broker)))


GOLDEN_CROSS_PARAMS = {
    "strategy_type": "moving_average_cross",
    "symbol_code": "005930",
    "short_window": 5,
    "long_window": 20,
    "quantity": 1,
    "timeframe": "1m",
    "enabled": True,
}


async def test_run_once_executes_active_strategy_and_saves_signal(db_session: AsyncSession) -> None:
    await _create_strategy_version(db_session, GOLDEN_CROSS_PARAMS)
    closes = [100] * 20 + [200]
    broker = FakeBrokerClient({"005930": _make_candles(closes)})

    results = await _runner(db_session, broker).run_once()

    assert len(results) == 1
    assert results[0].symbol_code == "005930"
    assert results[0].signal_created is True
    assert results[0].signal_id is not None
    assert results[0].auto_trade_enabled is False
    assert results[0].trade_attempted is False

    rows = (await db_session.execute(select(SignalLog))).scalars().all()
    assert len(rows) == 1


async def test_run_once_no_cross_saves_nothing(db_session: AsyncSession) -> None:
    await _create_strategy_version(db_session, GOLDEN_CROSS_PARAMS)
    closes = [100] * 21
    broker = FakeBrokerClient({"005930": _make_candles(closes)})

    results = await _runner(db_session, broker).run_once()

    assert len(results) == 1
    assert results[0].signal_created is False
    assert results[0].signal_id is None
    assert results[0].trade_attempted is False

    rows = (await db_session.execute(select(SignalLog))).scalars().all()
    assert rows == []


async def test_run_once_skips_inactive_and_disabled_strategies(db_session: AsyncSession) -> None:
    closes = [100] * 20 + [200]
    broker = FakeBrokerClient({"005930": _make_candles(closes)})

    await _create_strategy_version(db_session, GOLDEN_CROSS_PARAMS, status=StrategyVersionStatus.DRAFT)
    await _create_strategy_version(db_session, {**GOLDEN_CROSS_PARAMS, "enabled": False})
    await _create_strategy_version(db_session, {**GOLDEN_CROSS_PARAMS, "strategy_type": "rsi"})

    results = await _runner(db_session, broker).run_once()

    assert results == []


async def test_duplicate_candle_signal_not_saved_twice(db_session: AsyncSession) -> None:
    await _create_strategy_version(db_session, GOLDEN_CROSS_PARAMS)
    closes = [100] * 20 + [200]
    broker = FakeBrokerClient({"005930": _make_candles(closes)})

    runner = _runner(db_session, broker)

    first = await runner.run_once()
    second = await runner.run_once()

    assert len(first) == 1
    assert first[0].signal_created is True

    assert len(second) == 1
    assert second[0].signal_created is False
    assert second[0].signal_id is None

    rows = (await db_session.execute(select(SignalLog))).scalars().all()
    assert len(rows) == 1


async def test_symbol_httpx_error_does_not_crash_runner(db_session: AsyncSession) -> None:
    """한 종목에서 httpx.ReadTimeout이 발생해도 runner가 종료되지 않고 error를 기록한다."""
    await _create_strategy_version(db_session, GOLDEN_CROSS_PARAMS)
    broker = FakeBrokerClient(candles_error_by_symbol={"005930": httpx.ReadTimeout("timeout")})

    results = await _runner(db_session, broker).run_once()

    assert len(results) == 1
    assert results[0].signal_created is False
    assert results[0].error is not None
    assert "market data error" in results[0].error
    assert results[0].error_category == "connection_timeout"

    rows = (await db_session.execute(select(SignalLog))).scalars().all()
    assert rows == []


async def test_two_symbols_one_fails_other_succeeds(db_session: AsyncSession) -> None:
    """두 종목 중 하나가 httpx 오류를 내도 나머지는 정상 실행된다."""
    closes = [100] * 20 + [200]
    await _create_strategy_version(db_session, {**GOLDEN_CROSS_PARAMS, "symbol_code": "005930"})
    await _create_strategy_version(db_session, {**GOLDEN_CROSS_PARAMS, "symbol_code": "035720"})
    broker = FakeBrokerClient(
        candles_by_symbol={"035720": _make_candles(closes)},
        candles_error_by_symbol={"005930": httpx.ReadTimeout("timeout")},
    )

    results = await _runner(db_session, broker).run_once()

    assert len(results) == 2
    failing = next(r for r in results if r.symbol_code == "005930")
    succeeding = next(r for r in results if r.symbol_code == "035720")

    assert failing.error is not None
    assert failing.error_category == "connection_timeout"
    assert succeeding.signal_created is True
    assert succeeding.error is None

    rows = (await db_session.execute(select(SignalLog))).scalars().all()
    assert len(rows) == 1
