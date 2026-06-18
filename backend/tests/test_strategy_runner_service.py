from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.market_data import MarketData
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


# ---------------------------------------------------------------------------
# market_data 저장 통합 테스트
# ---------------------------------------------------------------------------


def _runner_with_db(session: AsyncSession, broker: BrokerClient) -> StrategyRunnerService:
    """session이 주입된 MarketDataService를 사용하는 runner."""
    return StrategyRunnerService(session, SignalService(session, MarketDataService(broker, session)))


async def test_run_once_saves_market_data_to_db(db_session: AsyncSession) -> None:
    """strategy runner 실행 시 KIS 분봉이 market_data 테이블에 저장된다."""
    await _create_strategy_version(db_session, GOLDEN_CROSS_PARAMS)
    closes = [100] * 20 + [200]
    broker = FakeBrokerClient({"005930": _make_candles(closes)})

    results = await _runner_with_db(db_session, broker).run_once()

    assert results[0].signal_created is True
    rows = (await db_session.execute(select(MarketData))).scalars().all()
    assert len(rows) == 21
    assert all(r.symbol_code == "005930" for r in rows)
    assert all(r.timeframe == "1m" for r in rows)


async def test_run_once_saves_market_data_even_when_no_signal(db_session: AsyncSession) -> None:
    """신호 미생성(크로스 없음)이어도 market_data는 저장된다."""
    await _create_strategy_version(db_session, GOLDEN_CROSS_PARAMS)
    closes = [100] * 21  # 크로스 없음
    broker = FakeBrokerClient({"005930": _make_candles(closes)})

    results = await _runner_with_db(db_session, broker).run_once()

    assert results[0].signal_created is False
    rows = (await db_session.execute(select(MarketData))).scalars().all()
    assert len(rows) == 21


async def test_run_twice_no_duplicate_market_data_rows(db_session: AsyncSession) -> None:
    """같은 분봉을 두 번 조회해도 market_data에 중복 row가 생기지 않는다."""
    await _create_strategy_version(db_session, GOLDEN_CROSS_PARAMS)
    closes = [100] * 20 + [200]
    broker = FakeBrokerClient({"005930": _make_candles(closes)})

    runner = _runner_with_db(db_session, broker)
    await runner.run_once()
    await runner.run_once()

    rows = (await db_session.execute(select(MarketData))).scalars().all()
    assert len(rows) == 21  # 중복 없음


class _FailingSaveMarketDataService(MarketDataService):
    """save_candles가 항상 실패하는 MarketDataService 서브클래스."""

    async def save_candles(self, symbol_code: str, timeframe: str, candles: list) -> int:
        raise RuntimeError("intentional DB failure")


async def test_market_data_save_failure_does_not_break_strategy_execution(
    db_session: AsyncSession,
) -> None:
    """market_data 저장 실패가 전략 신호 생성을 중단시키지 않는다."""
    await _create_strategy_version(db_session, GOLDEN_CROSS_PARAMS)
    closes = [100] * 20 + [200]
    broker = FakeBrokerClient({"005930": _make_candles(closes)})

    failing_svc = _FailingSaveMarketDataService(broker, db_session)
    runner = StrategyRunnerService(db_session, SignalService(db_session, failing_svc))
    results = await runner.run_once()

    assert len(results) == 1
    assert results[0].signal_created is True
    assert results[0].error is None

    # 저장은 실패했으므로 market_data는 0건
    rows = (await db_session.execute(select(MarketData))).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# C-2.16: Registry 통합 테스트
# ---------------------------------------------------------------------------


VOLUME_CONFIRMED_PARAMS = {
    "strategy_type": "volume_confirmed_ma_cross",
    "symbol_code": "005930",
    "short_window": 5,
    "long_window": 20,
    "volume_window": 20,
    "volume_multiplier": 1.5,
    "quantity": 1,
    "enabled": True,
}


def _make_candles_with_volume(
    closes: list[int], volumes: list[int]
) -> list[MinuteCandle]:
    candles = []
    for i, (close, vol) in enumerate(zip(closes, volumes)):
        price = Decimal(close)
        candles.append(
            MinuteCandle(
                business_date="20260610",
                trade_time=f"{900 + i:04d}00",
                open_price=price,
                high_price=price,
                low_price=price,
                close_price=price,
                volume=vol,
            )
        )
    return candles


async def test_runner_uses_registry_for_moving_average_cross(db_session: AsyncSession) -> None:
    """strategy_runner가 registry를 통해 moving_average_cross를 실행한다 (하드코딩 제거 확인)."""
    await _create_strategy_version(db_session, GOLDEN_CROSS_PARAMS)
    closes = [100] * 20 + [200]
    broker = FakeBrokerClient({"005930": _make_candles(closes)})

    results = await _runner(db_session, broker).run_once()

    assert len(results) == 1
    assert results[0].signal_created is True


async def test_runner_executes_volume_confirmed_ma_cross_strategy(db_session: AsyncSession) -> None:
    """volume_confirmed_ma_cross 전략이 runner(registry)를 통해 실행된다."""
    closes = [100] * 20 + [200]
    volumes = [1000] * 20 + [2000]  # 2000 >= 1000*1.5=1500 → volume_confirmed
    candles = _make_candles_with_volume(closes, volumes)

    await _create_strategy_version(db_session, VOLUME_CONFIRMED_PARAMS)
    broker = FakeBrokerClient({"005930": candles})

    results = await _runner(db_session, broker).run_once()

    assert len(results) == 1
    assert results[0].signal_created is True
    assert results[0].symbol_code == "005930"


async def test_runner_volume_confirmed_no_signal_when_volume_low(db_session: AsyncSession) -> None:
    """거래량 조건 미충족 시 volume_confirmed_ma_cross는 신호를 생성하지 않는다."""
    closes = [100] * 20 + [200]
    volumes = [1000] * 20 + [500]  # 500 < 1000*1.5=1500 → volume_confirmed=False
    candles = _make_candles_with_volume(closes, volumes)

    await _create_strategy_version(db_session, VOLUME_CONFIRMED_PARAMS)
    broker = FakeBrokerClient({"005930": candles})

    results = await _runner(db_session, broker).run_once()

    assert len(results) == 1
    assert results[0].signal_created is False


async def test_runner_unknown_strategy_type_is_skipped(db_session: AsyncSession) -> None:
    """알 수 없는 strategy_type은 결과 목록에 포함되지 않는다."""
    closes = [100] * 20 + [200]
    await _create_strategy_version(
        db_session, {**GOLDEN_CROSS_PARAMS, "strategy_type": "unknown_future_strategy"}
    )
    broker = FakeBrokerClient({"005930": _make_candles(closes)})

    results = await _runner(db_session, broker).run_once()

    assert results == []


async def test_runner_place_order_not_called(db_session: AsyncSession) -> None:
    """auto_trade_enabled=False인 전략에서 broker.place_order가 절대 호출되지 않는다."""
    import unittest.mock as mock

    closes = [100] * 20 + [200]
    volumes = [1000] * 20 + [2000]
    candles = _make_candles_with_volume(closes, volumes)

    broker = FakeBrokerClient({"005930": candles})
    broker.place_order = mock.AsyncMock(side_effect=AssertionError("place_order 호출 금지"))

    await _create_strategy_version(db_session, VOLUME_CONFIRMED_PARAMS)
    results = await _runner(db_session, broker).run_once()

    # place_order가 호출됐으면 AssertionError가 발생했을 것
    assert len(results) == 1
    assert results[0].trade_attempted is False
