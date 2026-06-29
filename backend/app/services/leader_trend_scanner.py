"""Leader Trend 메트릭 계산기 + 읽기 전용 후보 스캐너 (M2.15C-1).

주도주 추세추종(M2.15)의 52주 지표를 **이미 적재된 일봉(`market_data` timeframe="1d")** 만으로 계산하고
후보 A/B를 분류한다. **읽기 전용**: DB write 0 · 라이브 KIS 0 · SignalLog/Trade/Order 0 · 스케줄러/디스패처 0 ·
브로커/주문 경로 미사용. 후보 분류는 **매수 신호가 아니며**, 이 단계에서 영속화하지 않는다.

원주가(adjusted=False) 일봉은 분할/수정주가 미반영으로 비정상적 스케일(예: low_52w_gain 수백~수천%)을 만들 수
있어, 데이터 품질 경고로 **operationally_safe_for_classification=False** 를 표시한다(연구용 raw 라벨은 유지).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.models.market_data import MarketData

DAILY_TIMEFRAME = "1d"
REQUIRED_CANDLES = 252
COVERAGE_THRESHOLDS = (20, 50, 120, 252)

# 후보 필터(M2.15A 설계와 동일). **매수 신호 아님 · 후보 필터일 뿐.**
CAND_A_MAX_GAIN = 200.0      # low_52w_gain_pct <= 200
CAND_A_MAX_DRAWDOWN = 10.0   # drawdown_from_52w_high_pct <= 10
CAND_B_MIN_GAIN = 200.0      # low_52w_gain_pct >= 200
CAND_B_MAX_DRAWDOWN = 20.0   # drawdown_from_52w_high_pct <= 20

# 원주가/수정주가 스케일 위험 경고 임계값(데이터 품질만; 데이터 삭제 안 함).
RAW_RANGE_RATIO_WARN = 4.0       # high_52w / low_52w > 4 → 분할/수정주가 의심
RAW_GAIN_PCT_WARN = 500.0        # low_52w_gain_pct > 500% → 비정상 스케일 의심
RAW_DAY_JUMP_PCT_WARN = 50.0     # 일일 종가 점프 절댓값 > 50% → 분할/조정 의심

# candidate_bucket 정렬 우선순위(결정적 스캔 출력).
_BUCKET_RANK = {
    "A": 0, "B": 1,
    "A_raw_needs_adjusted_review": 2, "B_raw_needs_adjusted_review": 3,
    "none": 4, "insufficient_data": 5, "invalid_data": 6,
}


@dataclass
class LeaderTrendMetrics:
    symbol: str
    daily_count: int
    newest_date: str | None = None
    oldest_date: str | None = None
    current_close: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    low_52w_gain_pct: float | None = None
    drawdown_from_52w_high_pct: float | None = None
    ma20: float | None = None
    ma50: float | None = None
    recent_20d_high: float | None = None
    volume_20d_avg: int | None = None
    has_20: bool = False
    has_50: bool = False
    has_120: bool = False
    has_252: bool = False
    ready_for_52w: bool = False
    raw_candidate_a: bool = False
    raw_candidate_b: bool = False
    candidate_bucket: str = "insufficient_data"
    data_quality_warnings: list[str] = field(default_factory=list)
    operationally_safe_for_classification: bool = False

    def to_dict(self) -> dict:
        return {**self.__dict__}


def _round(v: float | None, ndigits: int = 2) -> float | None:
    return None if v is None else round(v, ndigits)


def compute_metrics(symbol: str, candles: list) -> LeaderTrendMetrics:
    """일봉 시퀀스(오름차순, ts/open/high/low/close/volume 보유 duck-typed)로 52주 지표 계산.

    순수 함수: DB/네트워크 미접촉. candles는 ts 오름차순 가정(아니면 내부 정렬). 가격은 Decimal/float 허용.
    """
    n = len(candles)
    m = LeaderTrendMetrics(symbol=symbol, daily_count=n)
    m.has_20 = n >= 20
    m.has_50 = n >= 50
    m.has_120 = n >= 120
    m.has_252 = n >= 252
    m.ready_for_52w = n >= REQUIRED_CANDLES

    if n == 0:
        m.candidate_bucket = "insufficient_data"
        return m

    # ts 오름차순 보장(결정적).
    rows = sorted(candles, key=lambda c: c.ts)
    closes, highs, lows, vols, dates = [], [], [], [], []
    invalid_reasons: list[str] = []
    seen_dates: set[str] = set()
    for c in rows:
        d = (c.ts.astimezone(KST)).strftime("%Y%m%d")
        if d in seen_dates:
            invalid_reasons.append(f"duplicate_date:{d}")
        seen_dates.add(d)
        try:
            o, h, lo, cl = float(c.open), float(c.high), float(c.low), float(c.close)
            v = int(c.volume)
        except (TypeError, ValueError):
            invalid_reasons.append("null_or_unparsable_ohlcv")
            continue
        if min(o, h, lo, cl) <= 0:
            invalid_reasons.append("nonpositive_price")
        if h < lo:
            invalid_reasons.append("high_lt_low")
        if cl < lo or cl > h:
            invalid_reasons.append("close_outside_low_high")
        closes.append(cl); highs.append(h); lows.append(lo); vols.append(v); dates.append(d)

    if dates:
        m.oldest_date, m.newest_date = dates[0], dates[-1]

    # hard-invalid → 지표는 계산하되 bucket=invalid_data, 분류 불가.
    if invalid_reasons or not closes:
        m.data_quality_warnings = sorted(set(invalid_reasons)) or ["no_valid_rows"]
        m.candidate_bucket = "invalid_data"
        m.operationally_safe_for_classification = False
        # 가능한 범위에서 참고 지표만.
        if closes:
            m.current_close = _round(closes[-1])
            m.high_52w = _round(max(highs)); m.low_52w = _round(min(lows))
        return m

    cur = closes[-1]
    hi = max(highs)
    lo = min(lows)
    m.current_close = _round(cur)
    m.high_52w = _round(hi)
    m.low_52w = _round(lo)
    m.low_52w_gain_pct = _round((cur / lo - 1.0) * 100.0) if lo > 0 else None
    m.drawdown_from_52w_high_pct = _round((hi - cur) / hi * 100.0) if hi > 0 else None
    m.ma20 = _round(sum(closes[-20:]) / min(20, n), 1) if n >= 20 else None
    m.ma50 = _round(sum(closes[-50:]) / min(50, n), 1) if n >= 50 else None
    m.recent_20d_high = _round(max(highs[-20:]), 2) if n >= 20 else None
    m.volume_20d_avg = int(sum(vols[-20:]) / min(20, n)) if n >= 20 else None

    # --- 데이터 품질: 원주가/수정주가 스케일 경고(데이터 삭제 없음) ---
    warnings: list[str] = []
    if lo > 0 and hi / lo > RAW_RANGE_RATIO_WARN:
        warnings.append(f"price_range_ratio_high:{round(hi/lo,2)}>{RAW_RANGE_RATIO_WARN}")
    if m.low_52w_gain_pct is not None and m.low_52w_gain_pct > RAW_GAIN_PCT_WARN:
        warnings.append(f"low_52w_gain_extreme:{m.low_52w_gain_pct}%>{RAW_GAIN_PCT_WARN}%")
    max_jump = 0.0
    for prev, nxt in zip(closes, closes[1:]):
        if prev > 0:
            j = abs(nxt / prev - 1.0) * 100.0
            max_jump = max(max_jump, j)
    if max_jump > RAW_DAY_JUMP_PCT_WARN:
        warnings.append(f"large_one_day_jump:{round(max_jump,1)}%>{RAW_DAY_JUMP_PCT_WARN}%")
    m.data_quality_warnings = warnings

    # --- 후보 분류(매수 신호 아님) ---
    gain, dd = m.low_52w_gain_pct, m.drawdown_from_52w_high_pct
    if gain is not None and dd is not None:
        m.raw_candidate_a = (gain <= CAND_A_MAX_GAIN) and (dd <= CAND_A_MAX_DRAWDOWN)
        m.raw_candidate_b = (gain >= CAND_B_MIN_GAIN) and (dd <= CAND_B_MAX_DRAWDOWN)

    has_blocking_warning = bool(warnings)
    if not m.ready_for_52w:
        m.candidate_bucket = "insufficient_data"
    elif m.raw_candidate_a:
        m.candidate_bucket = "A" if not has_blocking_warning else "A_raw_needs_adjusted_review"
    elif m.raw_candidate_b:
        m.candidate_bucket = "B" if not has_blocking_warning else "B_raw_needs_adjusted_review"
    else:
        m.candidate_bucket = "none"

    m.operationally_safe_for_classification = (
        m.ready_for_52w and not has_blocking_warning and not invalid_reasons
    )
    return m


class LeaderTrendScanner:
    """읽기 전용 스캐너. 명시 심볼 리스트의 `market_data` 1d만 읽어 메트릭/후보를 계산한다.

    **DB write 0 · 라이브 KIS 0 · SignalLog/Trade/Order 0 · broker/provider 미사용 · 스케줄러/디스패처 0.**
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _load_daily(self, symbol: str) -> list[MarketData]:
        stmt = (
            select(MarketData)
            .where(MarketData.symbol_code == symbol, MarketData.timeframe == DAILY_TIMEFRAME)
            .order_by(MarketData.ts.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def scan(self, symbols: list[str]) -> list[LeaderTrendMetrics]:
        results = [compute_metrics(s, await self._load_daily(s)) for s in symbols]
        results.sort(key=lambda m: (
            _BUCKET_RANK.get(m.candidate_bucket, 99),
            m.drawdown_from_52w_high_pct if m.drawdown_from_52w_high_pct is not None else float("inf"),
            -(m.low_52w_gain_pct if m.low_52w_gain_pct is not None else float("-inf")),
            m.symbol,
        ))
        return results
