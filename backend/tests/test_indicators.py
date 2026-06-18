"""indicators.py 신규 함수 테스트 (EMA, RSI, MACD, Volume SMA, Volume Ratio)."""
from decimal import Decimal

import pytest

from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.indicators import (
    MACDResult,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    calculate_volume_ratio,
    calculate_volume_sma,
)


def _make_candles(closes: list[int | float], volumes: list[int] | None = None) -> list[MinuteCandle]:
    if volumes is None:
        volumes = [1000] * len(closes)
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
    return candles


# ---------------------------------------------------------------------------
# 기존 calculate_sma 회귀 테스트
# ---------------------------------------------------------------------------


def test_sma_basic() -> None:
    candles = _make_candles([10, 20, 30])
    result = calculate_sma(candles, 3)
    assert result == Decimal("20")


def test_sma_insufficient_data_returns_none() -> None:
    candles = _make_candles([10, 20])
    assert calculate_sma(candles, 3) is None


# ---------------------------------------------------------------------------
# calculate_ema
# ---------------------------------------------------------------------------


def test_ema_returns_value_for_sufficient_data() -> None:
    candles = _make_candles([10] * 10)
    result = calculate_ema(candles, 5)
    assert result is not None
    # 모든 값이 동일하면 EMA == SMA == close
    assert result == Decimal("10")


def test_ema_insufficient_data_returns_none() -> None:
    candles = _make_candles([10, 20, 30])
    assert calculate_ema(candles, 5) is None


def test_ema_responds_faster_than_sma_on_price_spike() -> None:
    """가격 급등 시 EMA가 SMA보다 더 크게 반응한다.

    SMA(5)는 마지막 5개의 단순 평균인 반면, EMA는 최근 데이터를 지수적으로 더 가중한다.
    close=[100]*9 + [1000]: SMA(5)=(100*4+1000)/5=280, EMA > 280 (더 강하게 반응).
    """
    closes = [100] * 9 + [1000]
    candles = _make_candles(closes)
    ema = calculate_ema(candles, 5)
    sma = calculate_sma(candles, 5)
    assert ema is not None and sma is not None
    # EMA 씨드(100) + 급등(1000) → EMA ≈ 400 > SMA ≈ 280
    assert ema > sma


def test_ema_boundary_exactly_period_candles() -> None:
    """딱 period 개수 캔들이면 EMA = SMA = 해당 값."""
    candles = _make_candles([50] * 5)
    result = calculate_ema(candles, 5)
    assert result == Decimal("50")


# ---------------------------------------------------------------------------
# calculate_rsi
# ---------------------------------------------------------------------------


def test_rsi_flat_prices_returns_100() -> None:
    """가격 변화 없음 → avg_loss=0 → RSI=100."""
    candles = _make_candles([100] * 16)
    result = calculate_rsi(candles, period=14)
    assert result == Decimal("100")


def test_rsi_all_down_returns_zero() -> None:
    """계속 하락 → avg_gain=0 → RSI 낮음 (0에 가까움)."""
    closes = list(range(200, 184, -1))  # 16개, 200→185 하락
    candles = _make_candles(closes)
    result = calculate_rsi(candles, period=14)
    assert result is not None
    assert result < Decimal("10")


def test_rsi_insufficient_data_returns_none() -> None:
    candles = _make_candles([100] * 10)
    assert calculate_rsi(candles, period=14) is None


def test_rsi_value_in_range() -> None:
    """RSI는 항상 0~100 사이여야 한다."""
    closes = [100, 102, 98, 105, 95, 110, 88, 115, 92, 108, 96, 112, 100, 107, 103]
    candles = _make_candles(closes)
    result = calculate_rsi(candles, period=14)
    assert result is not None
    assert Decimal("0") <= result <= Decimal("100")


def test_rsi_boundary_period_plus_one_candles() -> None:
    """period+1개면 계산 가능."""
    candles = _make_candles([100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122, 124, 126, 128])
    result = calculate_rsi(candles, period=14)
    assert result is not None


# ---------------------------------------------------------------------------
# calculate_macd
# ---------------------------------------------------------------------------


def test_macd_returns_result_for_sufficient_data() -> None:
    closes = [100 + i for i in range(40)]  # 40개
    candles = _make_candles(closes)
    result = calculate_macd(candles, fast_period=12, slow_period=26, signal_period=9)
    assert result is not None
    assert isinstance(result, MACDResult)
    assert result.histogram == result.macd - result.signal


def test_macd_insufficient_data_returns_none() -> None:
    closes = [100] * 10
    candles = _make_candles(closes)
    assert calculate_macd(candles, fast_period=12, slow_period=26, signal_period=9) is None


def test_macd_exact_minimum_data() -> None:
    """slow_period + signal_period - 1 = 34개면 계산 가능."""
    closes = [100 + i for i in range(34)]
    candles = _make_candles(closes)
    result = calculate_macd(candles, fast_period=12, slow_period=26, signal_period=9)
    assert result is not None


def test_macd_uptrend_positive_macd() -> None:
    """강한 상승 추세에서 MACD 선은 양수여야 한다."""
    closes = list(range(100, 160))  # 60개, 지속 상승
    candles = _make_candles(closes)
    result = calculate_macd(candles)
    assert result is not None
    assert result.macd > Decimal("0")


# ---------------------------------------------------------------------------
# calculate_volume_sma
# ---------------------------------------------------------------------------


def test_volume_sma_basic() -> None:
    candles = _make_candles([100] * 5, volumes=[1000, 2000, 3000, 4000, 5000])
    result = calculate_volume_sma(candles, 5)
    assert result == Decimal("3000")


def test_volume_sma_uses_last_period() -> None:
    """마지막 period개만 사용한다."""
    candles = _make_candles([100] * 6, volumes=[9999, 1000, 1000, 1000, 1000, 1000])
    result = calculate_volume_sma(candles, 5)
    assert result == Decimal("1000")


def test_volume_sma_insufficient_data_returns_none() -> None:
    candles = _make_candles([100] * 3, volumes=[1000, 2000, 3000])
    assert calculate_volume_sma(candles, 5) is None


def test_volume_sma_boundary_exact_period() -> None:
    candles = _make_candles([100] * 5, volumes=[500] * 5)
    result = calculate_volume_sma(candles, 5)
    assert result == Decimal("500")


# ---------------------------------------------------------------------------
# calculate_volume_ratio
# ---------------------------------------------------------------------------


def test_volume_ratio_spike() -> None:
    """마지막 캔들 거래량이 SMA의 2배이면 ratio=2."""
    volumes = [1000] * 4 + [2000]
    candles = _make_candles([100] * 5, volumes=volumes)
    result = calculate_volume_ratio(candles, 5)
    assert result is not None
    # (1000*4 + 2000)/5 = 1200, 2000/1200 ≈ 1.667
    assert result > Decimal("1")


def test_volume_ratio_no_spike() -> None:
    """마지막 캔들 거래량이 평균 이하이면 ratio < 1."""
    volumes = [2000] * 4 + [500]
    candles = _make_candles([100] * 5, volumes=volumes)
    result = calculate_volume_ratio(candles, 5)
    assert result is not None
    assert result < Decimal("1")


def test_volume_ratio_zero_sma_returns_none() -> None:
    """거래량이 0이면 None."""
    candles = _make_candles([100] * 5, volumes=[0] * 5)
    assert calculate_volume_ratio(candles, 5) is None


def test_volume_ratio_insufficient_data_returns_none() -> None:
    candles = _make_candles([100] * 3, volumes=[1000] * 3)
    assert calculate_volume_ratio(candles, 5) is None
