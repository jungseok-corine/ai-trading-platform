"""C-4: 실전 전략 타입 4종(RSI 평균회귀·MACD 추세·돌파·눌림목) 단위 테스트."""
from decimal import Decimal

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.breakout_high import BreakoutHighStrategy
from app.trading.strategy.macd_trend import MacdTrendStrategy
from app.trading.strategy.pullback_trend import PullbackTrendStrategy
from app.trading.strategy.registry import create_strategy, registered_types
from app.trading.strategy.rsi_reversion import RsiReversionStrategy


def _candles(
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[int] | None = None,
) -> list[MinuteCandle]:
    """closes(오래된 순)로 캔들 리스트 생성. high/low/volume 미지정 시 close 기반 기본값."""
    out = []
    for i, close in enumerate(closes):
        c = Decimal(str(close))
        out.append(
            MinuteCandle(
                business_date="20260610",
                trade_time=f"{90000 + i:06d}",
                open_price=c,
                high_price=Decimal(str(highs[i])) if highs else c,
                low_price=Decimal(str(lows[i])) if lows else c,
                close_price=c,
                volume=volumes[i] if volumes else 1000,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 레지스트리 등록
# --------------------------------------------------------------------------- #


def test_new_types_registered() -> None:
    types = registered_types()
    for name in ("rsi_reversion", "macd_trend", "breakout_high", "pullback_trend"):
        assert name in types


def test_create_each_new_type() -> None:
    assert isinstance(create_strategy("rsi_reversion", {}), RsiReversionStrategy)
    assert isinstance(create_strategy("macd_trend", {}), MacdTrendStrategy)
    assert isinstance(create_strategy("breakout_high", {}), BreakoutHighStrategy)
    assert isinstance(create_strategy("pullback_trend", {}), PullbackTrendStrategy)


# --------------------------------------------------------------------------- #
# RSI 평균회귀
# --------------------------------------------------------------------------- #


def test_rsi_reversion_buy_on_oversold_exit() -> None:
    strategy = RsiReversionStrategy(rsi_period=14, oversold=Decimal("30"))
    # 길게 하락(과매도) 후 강하게 반등 → RSI가 30을 아래→위로 탈출 (prev<=30<curr)
    closes = [100 - i * 2 for i in range(18)] + [70, 74, 78]
    signal = strategy.generate_signal("005930", _candles(closes), strategy_version_id=1)
    assert signal is not None
    assert signal.side == TradeSide.BUY
    assert signal.metadata is not None and "rsi" in signal.metadata


def test_rsi_reversion_sell_on_overbought() -> None:
    strategy = RsiReversionStrategy(rsi_period=14, overbought=Decimal("70"), exit_mode="overbought")
    # 길게 상승 → RSI 과열(>=70)
    closes = [100 + i for i in range(21)]
    signal = strategy.generate_signal("005930", _candles(closes), strategy_version_id=1)
    assert signal is not None
    assert signal.side == TradeSide.SELL


def test_rsi_reversion_insufficient_candles() -> None:
    strategy = RsiReversionStrategy(rsi_period=14)
    assert strategy.generate_signal("005930", _candles([100] * 10)) is None


# --------------------------------------------------------------------------- #
# MACD 추세추종
# --------------------------------------------------------------------------- #


def test_macd_trend_buy_on_bullish_cross() -> None:
    strategy = MacdTrendStrategy()
    # 하락 끝에 반등 캔들이 들어오며 MACD가 시그널선을 마지막 캔들에서 상향 교차
    closes = [100 - i for i in range(34)] + [71]
    signal = strategy.generate_signal("005930", _candles(closes), strategy_version_id=1)
    assert signal is not None
    assert signal.side == TradeSide.BUY
    assert signal.metadata is not None and "macd" in signal.metadata


def test_macd_trend_sell_on_bearish_cross() -> None:
    strategy = MacdTrendStrategy()
    # 상승 끝에 하락 캔들이 들어오며 MACD가 시그널선을 마지막 캔들에서 하향 교차
    closes = [100 + i for i in range(34)] + [129]
    signal = strategy.generate_signal("005930", _candles(closes), strategy_version_id=1)
    assert signal is not None
    assert signal.side == TradeSide.SELL


def test_macd_trend_insufficient_candles() -> None:
    assert MacdTrendStrategy().generate_signal("005930", _candles([100] * 20)) is None


# --------------------------------------------------------------------------- #
# 전고점 돌파
# --------------------------------------------------------------------------- #


def test_breakout_high_buy_on_new_high() -> None:
    strategy = BreakoutHighStrategy(breakout_lookback=20, exit_lookback=10)
    # 20봉 박스권(고가 110) 후 마지막에 돌파(120)
    closes = [100] * 20 + [120]
    highs = [110] * 20 + [120]
    signal = strategy.generate_signal("005930", _candles(closes, highs=highs), strategy_version_id=1)
    assert signal is not None
    assert signal.side == TradeSide.BUY


def test_breakout_high_volume_confirm_blocks_without_spike() -> None:
    strategy = BreakoutHighStrategy(
        breakout_lookback=20, volume_confirm=True, volume_window=20, volume_multiplier=Decimal("2.0")
    )
    closes = [100] * 20 + [120]
    highs = [110] * 20 + [120]
    volumes = [1000] * 21  # spike 없음
    signal = strategy.generate_signal(
        "005930", _candles(closes, highs=highs, volumes=volumes), strategy_version_id=1
    )
    assert signal is None  # 거래량 미확인 → BUY 차단


def test_breakout_high_sell_on_breakdown() -> None:
    strategy = BreakoutHighStrategy(breakout_lookback=20, exit_lookback=10)
    # 박스권(저가 90) 후 마지막에 하단 이탈(80)
    closes = [100] * 20 + [80]
    lows = [90] * 20 + [80]
    signal = strategy.generate_signal("005930", _candles(closes, lows=lows), strategy_version_id=1)
    assert signal is not None
    assert signal.side == TradeSide.SELL


# --------------------------------------------------------------------------- #
# 눌림목 매수
# --------------------------------------------------------------------------- #


def test_pullback_trend_buy_on_reclaim_in_uptrend() -> None:
    strategy = PullbackTrendStrategy(short_window=10, long_window=50)
    # 꾸준한 상승추세(종가>장기MA) 중 직전에 단기선 아래로 눌렸다가 현재 재탈환
    closes = [100 + i for i in range(52)]  # 우상향 → 종가가 장기MA 위 (장기50+1 캔들 이상)
    closes[-2] = closes[-3] - 8  # 직전 캔들만 눌림(단기MA 아래)
    closes[-1] = closes[-3] + 3  # 현재 재탈환
    signal = strategy.generate_signal("005930", _candles(closes), strategy_version_id=1)
    assert signal is not None
    assert signal.side == TradeSide.BUY


def test_pullback_trend_sell_on_trend_break() -> None:
    strategy = PullbackTrendStrategy(short_window=10, long_window=50)
    # 상승추세 끝에 급락하여 장기MA 하향 이탈
    closes = [100 + i for i in range(50)] + [60]
    signal = strategy.generate_signal("005930", _candles(closes), strategy_version_id=1)
    assert signal is not None
    assert signal.side == TradeSide.SELL


def test_pullback_trend_insufficient_candles() -> None:
    assert PullbackTrendStrategy(long_window=50).generate_signal("005930", _candles([100] * 30)) is None
