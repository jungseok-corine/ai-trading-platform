from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence
from app.common.timezone import KST

from app.trading.broker.schemas import MinuteCandle



def calculate_sma(candles: list[MinuteCandle], period: int) -> Decimal | None:
    """candles(오래된 순)의 마지막 period개 종가 단순이동평균(SMA)을 계산한다.

    데이터가 부족하면 None을 반환한다.
    """
    if len(candles) < period:
        return None
    closes = [c.close_price for c in candles[-period:]]
    return sum(closes, Decimal(0)) / period


def candle_timestamp(candle: MinuteCandle) -> datetime:
    """분봉의 business_date + trade_time을 KST datetime으로 변환한다."""
    return datetime.strptime(
        f"{candle.business_date}{candle.trade_time}", "%Y%m%d%H%M%S"
    ).replace(tzinfo=KST)


def _ema_from_values(values: Sequence[Decimal], period: int) -> Decimal | None:
    """Decimal 시퀀스에 EMA를 적용하는 내부 헬퍼. 시드는 첫 period개의 SMA."""
    if len(values) < period:
        return None
    k = Decimal(2) / (period + 1)
    ema = sum(values[:period], Decimal(0)) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def calculate_ema(candles: list[MinuteCandle], period: int) -> Decimal | None:
    """지수이동평균(EMA)을 계산한다. 데이터 부족 시 None."""
    if len(candles) < period:
        return None
    return _ema_from_values([c.close_price for c in candles], period)


def calculate_rsi(candles: list[MinuteCandle], period: int = 14) -> Decimal | None:
    """RSI(Relative Strength Index)를 계산한다.

    period+1개 이상의 캔들이 필요하다.
    - 상승만 있고 하락이 없으면(avg_loss=0, avg_gain>0) RSI=100.
    - 가격 변화가 전혀 없으면(avg_gain=avg_loss=0) RSI는 정의되지 않으므로 None을 반환한다.
      (장 마감 후 시세가 종가로 평탄하게 채워진 스테일 캔들이 '과열(RSI=100)'로
      오인되어 허위 매도 신호를 내는 것을 방지한다.)
    """
    if len(candles) < period + 1:
        return None
    closes = [c.close_price for c in candles]
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    last_changes = changes[-period:]
    avg_gain = sum((max(c, Decimal(0)) for c in last_changes), Decimal(0)) / period
    avg_loss = sum((max(-c, Decimal(0)) for c in last_changes), Decimal(0)) / period
    if avg_loss == Decimal(0):
        # 완전 평탄(상승·하락 모두 없음) → RSI 정의 불가 → None
        if avg_gain == Decimal(0):
            return None
        return Decimal(100)
    rs = avg_gain / avg_loss
    return Decimal(100) - Decimal(100) / (1 + rs)


@dataclass
class MACDResult:
    macd: Decimal      # MACD 선 = EMA(fast) - EMA(slow)
    signal: Decimal    # 시그널 선 = EMA(macd, signal_period)
    histogram: Decimal  # MACD - signal


def calculate_macd(
    candles: list[MinuteCandle],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> MACDResult | None:
    """MACD 지표를 계산한다.

    slow_period + signal_period - 1개 이상의 캔들이 필요하다.
    """
    if len(candles) < slow_period + signal_period - 1:
        return None
    closes = [c.close_price for c in candles]
    # slow_period 번째부터 MACD 시계열 생성
    macd_series: list[Decimal] = []
    for i in range(slow_period - 1, len(closes)):
        sub = closes[: i + 1]
        fast = _ema_from_values(sub, fast_period)
        slow = _ema_from_values(sub, slow_period)
        if fast is not None and slow is not None:
            macd_series.append(fast - slow)
    if len(macd_series) < signal_period:
        return None
    signal_val = _ema_from_values(macd_series, signal_period)
    if signal_val is None:
        return None
    macd_val = macd_series[-1]
    return MACDResult(macd=macd_val, signal=signal_val, histogram=macd_val - signal_val)


def calculate_volume_sma(candles: list[MinuteCandle], period: int) -> Decimal | None:
    """마지막 period개 캔들의 거래량 단순이동평균을 계산한다. 데이터 부족 시 None."""
    if len(candles) < period:
        return None
    volumes = [Decimal(c.volume) for c in candles[-period:]]
    return sum(volumes, Decimal(0)) / period


def calculate_volume_ratio(candles: list[MinuteCandle], period: int) -> Decimal | None:
    """현재 거래량 / Volume SMA 비율을 반환한다.

    volume_sma가 0이거나 데이터 부족이면 None. 1.5 이상이면 spike 수준으로 본다.
    """
    vsma = calculate_volume_sma(candles, period)
    if vsma is None or vsma == Decimal(0):
        return None
    return Decimal(candles[-1].volume) / vsma


# ── C-7.1 DSL 지표 어휘 확장 ──────────────────────────────────────────────


def calculate_stddev(candles: list[MinuteCandle], period: int) -> Decimal | None:
    """종가 표준편차 (모집단). 데이터 부족 시 None."""
    if period <= 0 or len(candles) < period:
        return None
    closes = [c.close_price for c in candles[-period:]]
    mean = sum(closes) / period
    variance = sum((c - mean) ** 2 for c in closes) / period
    return variance.sqrt()


def calculate_bollinger(
    candles: list[MinuteCandle], period: int = 20, num_std: float = 2.0
) -> tuple[Decimal, Decimal, Decimal] | None:
    """볼린저 밴드 (mid, upper, lower). 데이터 부족 시 None."""
    mid = calculate_sma(candles, period)
    std = calculate_stddev(candles, period)
    if mid is None or std is None:
        return None
    width = std * Decimal(str(num_std))
    return mid, mid + width, mid - width


def calculate_atr(candles: list[MinuteCandle], period: int = 14) -> Decimal | None:
    """ATR (True Range 단순평균). 데이터 부족 시 None."""
    if period <= 0 or len(candles) < period + 1:
        return None
    trs = []
    window = candles[-(period + 1):]
    for prev, cur in zip(window, window[1:]):
        tr = max(
            cur.high_price - cur.low_price,
            abs(cur.high_price - prev.close_price),
            abs(cur.low_price - prev.close_price),
        )
        trs.append(tr)
    return sum(trs) / len(trs)


def calculate_highest_high(candles: list[MinuteCandle], period: int) -> Decimal | None:
    """직전 period봉(현재 봉 제외)의 최고가 — 돌파 판정용 (돈치안 상단)."""
    if period <= 0 or len(candles) < period + 1:
        return None
    return max(c.high_price for c in candles[-(period + 1):-1])


def calculate_lowest_low(candles: list[MinuteCandle], period: int) -> Decimal | None:
    """직전 period봉(현재 봉 제외)의 최저가 (돈치안 하단)."""
    if period <= 0 or len(candles) < period + 1:
        return None
    return min(c.low_price for c in candles[-(period + 1):-1])


def calculate_stochastic_k(candles: list[MinuteCandle], period: int = 14) -> Decimal | None:
    """스토캐스틱 %K (fast). 레인지 0이면 None."""
    if period <= 0 or len(candles) < period:
        return None
    window = candles[-period:]
    hi = max(c.high_price for c in window)
    lo = min(c.low_price for c in window)
    if hi == lo:
        return None
    return (candles[-1].close_price - lo) / (hi - lo) * 100


def calculate_return_pct(candles: list[MinuteCandle], lookback: int) -> Decimal | None:
    """lookback봉 전 종가 대비 수익률(%)."""
    if lookback <= 0 or len(candles) < lookback + 1:
        return None
    base = candles[-(lookback + 1)].close_price
    if base <= 0:
        return None
    return (candles[-1].close_price - base) / base * 100
