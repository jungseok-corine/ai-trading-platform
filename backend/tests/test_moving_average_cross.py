from decimal import Decimal

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.moving_average_cross import MovingAverageCrossStrategy


def _make_candles(closes: list[int]) -> list[MinuteCandle]:
    """closes(오래된 순)를 종가로 하는 1분봉 리스트를 생성한다."""
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


def test_golden_cross_returns_buy_signal() -> None:
    strategy = MovingAverageCrossStrategy(short_window=5, long_window=20)
    # 처음 20개는 100으로 평탄 (단기==장기), 마지막 1개가 급등 -> 단기선이 장기선을 상향 돌파
    closes = [100] * 20 + [200]
    candles = _make_candles(closes)

    signal = strategy.generate_signal("005930", candles, strategy_version_id=1)

    assert signal is not None
    assert signal.side == TradeSide.BUY
    assert signal.symbol_code == "005930"
    assert signal.strategy_version_id == 1
    assert signal.metadata is not None
    assert signal.metadata["short_ma"] > signal.metadata["long_ma"]


def test_dead_cross_returns_sell_signal() -> None:
    strategy = MovingAverageCrossStrategy(short_window=5, long_window=20)
    # 처음 20개는 100으로 평탄, 마지막 1개가 급락 -> 단기선이 장기선을 하향 돌파
    closes = [100] * 20 + [0]
    candles = _make_candles(closes)

    signal = strategy.generate_signal("005930", candles, strategy_version_id=1)

    assert signal is not None
    assert signal.side == TradeSide.SELL
    assert signal.metadata is not None
    assert signal.metadata["short_ma"] < signal.metadata["long_ma"]


def test_no_cross_returns_none() -> None:
    strategy = MovingAverageCrossStrategy(short_window=5, long_window=20)
    # 모든 종가가 동일 -> 단기==장기, 교차 없음
    closes = [100] * 21
    candles = _make_candles(closes)

    signal = strategy.generate_signal("005930", candles, strategy_version_id=1)

    assert signal is None


def test_insufficient_candles_returns_none() -> None:
    strategy = MovingAverageCrossStrategy(short_window=5, long_window=20)
    closes = [100] * 10
    candles = _make_candles(closes)

    signal = strategy.generate_signal("005930", candles, strategy_version_id=1)

    assert signal is None
