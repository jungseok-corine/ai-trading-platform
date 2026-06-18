from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import TradeSide
from app.domain.models.watchlist import Watchlist, WatchlistSymbol
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
from app.trading.strategy.volume_confirmed_ma_cross import VolumeConfirmedMovingAverageCrossStrategy


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


async def _create_watchlist_symbol(
    session: AsyncSession, symbol_code: str, symbol_name: str
) -> None:
    watchlist = Watchlist(name=f"test_{symbol_code}")
    session.add(watchlist)
    await session.flush()
    session.add(WatchlistSymbol(watchlist_id=watchlist.id, symbol_code=symbol_code, symbol_name=symbol_name))
    await session.flush()


async def test_list_signals_includes_symbol_display_when_watchlist_has_name(
    db_session: AsyncSession,
) -> None:
    await _create_watchlist_symbol(db_session, "005930", "삼성전자")

    closes = [100] * 20 + [200]
    broker = FakeBrokerClient(_make_candles(closes))
    service = SignalService(db_session, MarketDataService(broker))
    await service.generate_and_log_signal(MovingAverageCrossStrategy(), "005930")

    logs = await service.list_signals()
    assert len(logs) == 1
    assert logs[0].symbol_code == "005930"
    assert logs[0].symbol_name == "삼성전자"
    assert logs[0].symbol_display == "삼성전자 (005930)"


async def test_list_signals_symbol_display_is_none_when_no_watchlist_entry(
    db_session: AsyncSession,
) -> None:
    closes = [100] * 20 + [200]
    broker = FakeBrokerClient(_make_candles(closes))
    service = SignalService(db_session, MarketDataService(broker))
    await service.generate_and_log_signal(MovingAverageCrossStrategy(), "005930")

    logs = await service.list_signals()
    assert len(logs) == 1
    assert logs[0].symbol_code == "005930"
    assert logs[0].symbol_name is None
    assert logs[0].symbol_display is None


async def test_get_signal_includes_symbol_display_when_watchlist_has_name(
    db_session: AsyncSession,
) -> None:
    await _create_watchlist_symbol(db_session, "035420", "NAVER")

    closes = [100] * 20 + [200]
    broker = FakeBrokerClient(_make_candles(closes))
    service = SignalService(db_session, MarketDataService(broker))
    log = await service.generate_and_log_signal(MovingAverageCrossStrategy(), "035420")
    assert log is not None

    fetched = await service.get_signal(log.id)
    assert fetched is not None
    assert fetched.symbol_name == "NAVER"
    assert fetched.symbol_display == "NAVER (035420)"


async def test_symbol_code_is_preserved_in_all_cases(db_session: AsyncSession) -> None:
    await _create_watchlist_symbol(db_session, "000660", "SK하이닉스")

    closes = [100] * 20 + [200]
    broker = FakeBrokerClient(_make_candles(closes))
    service = SignalService(db_session, MarketDataService(broker))
    await service.generate_and_log_signal(MovingAverageCrossStrategy(), "000660")

    logs = await service.list_signals()
    assert len(logs) == 1
    assert logs[0].symbol_code == "000660"


# ---------------------------------------------------------------------------
# 테스트 #13: signal_logs.indicators 지표 영속화 (A안)
# ---------------------------------------------------------------------------


async def test_indicators_saved_for_volume_confirmed_strategy(db_session: AsyncSession) -> None:
    """VolumeConfirmedMovingAverageCrossStrategy 신호가 저장될 때
    indicators JSONB 컬럼에 volume 지표가 포함되어야 한다."""
    # 골든크로스 + 거래량 spike 조건: close 급등 + volume 2000 >= 1000*1.5=1500
    closes = [100] * 20 + [200]
    volumes = [1000] * 20 + [2000]
    candles = []
    for i, (close, vol) in enumerate(zip(closes, volumes)):
        price = Decimal(str(close))
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

    broker = FakeBrokerClient(candles)
    service = SignalService(db_session, MarketDataService(broker))
    strategy = VolumeConfirmedMovingAverageCrossStrategy(
        short_window=5, long_window=20, volume_window=20, volume_multiplier=Decimal("1.5")
    )

    log = await service.generate_and_log_signal(strategy, "005930")

    assert log is not None
    assert log.signal_type == TradeSide.BUY
    # indicators 컬럼 확인
    assert log.indicators is not None
    assert "volume_ratio" in log.indicators
    assert "volume_sma" in log.indicators
    assert "volume_confirmed" in log.indicators
    assert log.indicators["volume_confirmed"] is True
    # short_sma/long_sma도 저장됨
    assert "short_sma" in log.indicators
    assert "long_sma" in log.indicators


async def test_indicators_none_for_moving_average_cross_strategy(db_session: AsyncSession) -> None:
    """기존 MovingAverageCrossStrategy 신호는 indicators가 None이거나 빈 dict여야 한다.

    MA cross metadata에는 short_ma, long_ma, candle_ts만 있으므로
    모두 skip되어 indicators=None이 된다.
    """
    closes = [100] * 20 + [200]
    candles = []
    for i, close in enumerate(closes):
        price = Decimal(str(close))
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

    broker = FakeBrokerClient(candles)
    service = SignalService(db_session, MarketDataService(broker))

    log = await service.generate_and_log_signal(MovingAverageCrossStrategy(), "005930")

    assert log is not None
    # MA cross는 volume 지표 없음 → indicators=None (하위호환 유지)
    assert log.indicators is None
