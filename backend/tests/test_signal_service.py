from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import TradeSide
from app.services.market_data_service import MarketDataService
from app.services.signal_service import SignalService
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
from app.trading.strategy.moving_average_cross import MovingAverageCrossStrategy


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
    """SignalService 테스트용 — 고정된 분봉 데이터를 반환한다."""

    def __init__(self, candles: list[MinuteCandle]) -> None:
        self._candles = candles

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        return self._candles

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

    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
        raise NotImplementedError


async def test_generate_and_log_signal_saves_golden_cross(db_session: AsyncSession) -> None:
    closes = [100] * 20 + [200]
    broker = FakeBrokerClient(_make_candles(closes))
    service = SignalService(db_session, MarketDataService(broker))

    log = await service.generate_and_log_signal(MovingAverageCrossStrategy(), "005930")

    assert log is not None
    assert log.symbol_code == "005930"
    assert log.signal_type == TradeSide.BUY
    assert log.short_ma > log.long_ma
    assert log.price == Decimal("200")

    fetched = await service.get_signal(log.id)
    assert fetched is not None
    assert fetched.id == log.id

    logs = await service.list_signals()
    assert len(logs) == 1
    assert logs[0].id == log.id


async def test_generate_and_log_signal_returns_none_without_cross(db_session: AsyncSession) -> None:
    closes = [100] * 21
    broker = FakeBrokerClient(_make_candles(closes))
    service = SignalService(db_session, MarketDataService(broker))

    log = await service.generate_and_log_signal(MovingAverageCrossStrategy(), "005930")

    assert log is None
    assert await service.list_signals() == []


async def test_list_signals_returns_newest_first(db_session: AsyncSession) -> None:
    """list_signals는 generated_at DESC, id DESC 순으로 반환한다."""
    # 골든 크로스 두 번: 두 번째 시그널이 나중에 생성됨
    closes = [100] * 20 + [200]
    broker = FakeBrokerClient(_make_candles(closes))
    service = SignalService(db_session, MarketDataService(broker))

    log1 = await service.generate_and_log_signal(MovingAverageCrossStrategy(), "005930")
    assert log1 is not None

    # candle_ts가 달라야 중복 방지 로직을 우회하므로 다른 종목으로 두 번째 신호 생성
    log2 = await service.generate_and_log_signal(MovingAverageCrossStrategy(), "000660")
    assert log2 is not None

    logs = await service.list_signals()
    assert len(logs) == 2
    # 나중에 생성된 log2가 첫 번째여야 한다
    assert logs[0].id == log2.id
    assert logs[1].id == log1.id
