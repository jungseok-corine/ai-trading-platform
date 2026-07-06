"""종목 추세성(trendiness) 분류 — 순수 함수 (C-6.22, D-31 실행).

"만능 전략은 없다"(D-31): breakout은 추세 종목 전용(횡보 종목 1년 -43%),
rsi_reversion은 횡보·하락 방어 전용. 이 모듈은 일봉으로 종목을 trend/range로
분류해 배정(assignment)이 종목 특성에 맞는 strategy_type을 고르게 한다.

라벨은 기존 regime_fit 어휘("trend"/"range", 선정 보드·카탈로그와 동일)를 재사용한다.
순수 함수 — DB/네트워크 미접촉.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TREND = "trend"
RANGE = "range"
UNKNOWN = "unknown"

# 분류에 필요한 최소 일봉 수(MA50 + 여유). 미만이면 unknown(분류 안 함 = 기존 동작 유지).
MIN_DAILY_CANDLES = 50
# 추세 판정: 최근 lookback(기본 60일) 수익률 하한.
TREND_MIN_RETURN_PCT = 10.0
DEFAULT_LOOKBACK_DAYS = 60

# strategy_type → 적합 추세성. 미등재 타입은 필터링하지 않는다(항상 호환).
# 추세추종 계열 = trend 전용, 평균회귀(rsi) = range(횡보·하락 방어) 전용.
STRATEGY_FIT: dict[str, str] = {
    "breakout_high": TREND,
    "momentum_surge": TREND,
    "macd_trend": TREND,
    "moving_average_cross": TREND,
    "pullback_trend": TREND,
    "rsi_reversion": RANGE,
}


@dataclass
class TrendinessResult:
    classification: str = UNKNOWN     # trend / range / unknown
    daily_count: int = 0
    return_lookback_pct: float | None = None
    ma20: float | None = None
    ma50: float | None = None
    close: float | None = None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {**self.__dict__}


def classify_trendiness(
    candles: list,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    trend_min_return_pct: float = TREND_MIN_RETURN_PCT,
) -> TrendinessResult:
    """일봉 시퀀스(duck-typed: ts/close)로 종목 추세성을 분류한다.

    - trend: MA20 > MA50 이고 종가 > MA50 이고 lookback 수익률 >= 하한 — 추세추종 우호.
    - range: 그 외(횡보·하락 포함) — 평균회귀/방어 우호.
    - unknown: 일봉 부족(MIN_DAILY_CANDLES 미만) 또는 파싱 불가 — 분류하지 않음.
    """
    r = TrendinessResult(daily_count=len(candles))
    if len(candles) < MIN_DAILY_CANDLES:
        r.reasons.append(f"insufficient_daily_candles:{len(candles)}<{MIN_DAILY_CANDLES}")
        return r

    rows = sorted(candles, key=lambda c: c.ts)
    closes: list[float] = []
    for c in rows:
        try:
            cl = float(c.close)
        except (TypeError, ValueError):
            r.reasons.append("unparsable_close")
            return r
        if cl <= 0:
            r.reasons.append("nonpositive_close")
            return r
        closes.append(cl)

    cur = closes[-1]
    window = closes[-lookback_days:]
    base = window[0]
    ret_pct = (cur / base - 1.0) * 100.0
    ma20 = sum(closes[-20:]) / 20
    ma50 = sum(closes[-50:]) / 50

    r.close = round(cur, 2)
    r.return_lookback_pct = round(ret_pct, 2)
    r.ma20 = round(ma20, 2)
    r.ma50 = round(ma50, 2)

    if ma20 > ma50 and cur > ma50 and ret_pct >= trend_min_return_pct:
        r.classification = TREND
        r.reasons.append(
            f"ma20>ma50, close>ma50, return_{lookback_days}d={r.return_lookback_pct}%"
            f">={trend_min_return_pct}%"
        )
    else:
        r.classification = RANGE
        if ma20 <= ma50:
            r.reasons.append("ma20<=ma50")
        if cur <= ma50:
            r.reasons.append("close<=ma50")
        if ret_pct < trend_min_return_pct:
            r.reasons.append(
                f"return_{lookback_days}d={r.return_lookback_pct}%<{trend_min_return_pct}%"
            )
    return r


def is_compatible(strategy_type: str, classification: str) -> bool:
    """strategy_type이 종목 추세성과 호환되는지. unknown/미등재 타입은 항상 호환."""
    if classification == UNKNOWN:
        return True
    fit = STRATEGY_FIT.get(strategy_type)
    return fit is None or fit == classification
