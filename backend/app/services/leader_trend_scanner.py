"""Leader Trend 메트릭 계산기 + 읽기 전용 후보 스캐너 (M2.15C-1 → M2.15C-4 계층화).

주도주 추세추종(M2.15)의 52주 지표를 **이미 적재된 일봉(`market_data` timeframe="1d")** 만으로 계산하고
후보 A/B를 분류한다. **읽기 전용**: DB write 0 · 라이브 KIS 0 · SignalLog/Trade/Order 0 · 스케줄러/디스패처 0 ·
브로커/주문 경로 미사용. 후보 분류는 **매수 신호가 아니며**, 이 단계에서 영속화하지 않는다.

M2.15C-4 정책(M2.15C-3 결정): 경고를 **3계층으로 분리**한다.
- **hard_errors**(데이터 무결성 결함) → `invalid_data`, 운영/연구 분류 불가.
- **adjustment_warnings**(분할/조정 의심: 미설명 일일 종가 점프 >50%) → 후보면 `*_raw_needs_adjusted_review`,
  `operationally_safe_for_classification=False`.
- **strategy_extreme_warnings**(대형 52주 range/gain: 강한 주도주 신호) → **비차단**. `is_strategy_extreme=True`만
  표시하고 운영 분류를 막지 않는다(Candidate B는 본래 큰 gain을 노린다 — M2.15C-2/3).
연구(`candidate_bucket_research`)는 경고 무관 A/B 그대로, 운영(`candidate_bucket_operational`)은 위 규칙 반영.
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

# 검증된 파일럿 유니버스(M2.15B-9 적재 + M2.15D-3A 실전 도메인 검증). 노출 기본 범위.
PILOT_SYMBOLS = ["005930", "000660", "035420", "005380", "051910"]
MAX_SCAN_SYMBOLS = 5  # 노출 API 상한(20/110/전체 확장 금지 — 별도 승인 전까지).
# 운영 후보로 카운트하는 운영 bucket(매수 신호 아님 · 연구 후보 분류일 뿐).
OPERATIONAL_CANDIDATE_BUCKETS = ("A", "B")

# 후보 필터(M2.15A 설계와 동일). **매수 신호 아님 · 후보 필터일 뿐.**
CAND_A_MAX_GAIN = 200.0      # low_52w_gain_pct <= 200
CAND_A_MAX_DRAWDOWN = 10.0   # drawdown_from_52w_high_pct <= 10
CAND_B_MIN_GAIN = 200.0      # low_52w_gain_pct >= 200
CAND_B_MAX_DRAWDOWN = 20.0   # drawdown_from_52w_high_pct <= 20

# 전략-극단 경고 임계값(M2.15C-4: **비차단**, 강한 주도주 신호이지 데이터 결함 아님).
STRATEGY_EXTREME_RANGE_RATIO = 4.0   # high_52w / low_52w > 4
STRATEGY_EXTREME_GAIN_PCT = 500.0    # low_52w_gain_pct > 500%
# 분할/조정 의심 임계값(M2.15C-4: **운영 차단**, 미설명 가격 불연속).
ADJUSTMENT_DAY_JUMP_PCT = 50.0       # 일일 종가 점프 절댓값 > 50%

# 운영 bucket 정렬 우선순위(결정적 스캔 출력).
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
    # --- M2.15C-4 계층화 경고/상태 ---
    hard_errors: list[str] = field(default_factory=list)
    data_quality_warnings: list[str] = field(default_factory=list)
    adjustment_warnings: list[str] = field(default_factory=list)
    strategy_extreme_warnings: list[str] = field(default_factory=list)
    is_data_valid: bool = True
    is_adjustment_suspect: bool = False
    is_strategy_extreme: bool = False
    candidate_bucket_research: str = "insufficient_data"
    candidate_bucket_operational: str = "insufficient_data"
    operationally_safe_for_classification: bool = False
    # 하위 호환: 기존 candidate_bucket = 운영 bucket 별칭.
    candidate_bucket: str = "insufficient_data"

    def to_dict(self) -> dict:
        return {**self.__dict__}


def _round(v: float | None, ndigits: int = 2) -> float | None:
    return None if v is None else round(v, ndigits)


def compute_metrics(symbol: str, candles: list) -> LeaderTrendMetrics:
    """일봉 시퀀스(오름차순, ts/open/high/low/close/volume 보유 duck-typed)로 52주 지표 + 계층화 분류.

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
        # 행이 없음 = 무결성 결함이 아니라 데이터 부족 → insufficient_data.
        _finalize(m)
        return m

    rows = sorted(candles, key=lambda c: c.ts)  # ts 오름차순 보장(결정적).
    closes, highs, lows, vols, dates = [], [], [], [], []
    hard_errors: list[str] = []
    seen_dates: set[str] = set()
    for c in rows:
        d = (c.ts.astimezone(KST)).strftime("%Y%m%d")
        if d in seen_dates:
            hard_errors.append(f"duplicate_date:{d}")
        seen_dates.add(d)
        try:
            o, h, lo, cl = float(c.open), float(c.high), float(c.low), float(c.close)
            v = int(c.volume)
        except (TypeError, ValueError):
            hard_errors.append("null_or_unparsable_ohlcv")
            continue
        if min(o, h, lo, cl) <= 0:
            hard_errors.append("nonpositive_price")
        if h < lo:
            hard_errors.append("high_lt_low")
        if cl < lo or cl > h:
            hard_errors.append("close_outside_low_high")
        closes.append(cl); highs.append(h); lows.append(lo); vols.append(v); dates.append(d)

    if dates:
        m.oldest_date, m.newest_date = dates[0], dates[-1]

    # hard-invalid → 지표는 참고로만 계산하고 invalid_data 처리(연구/운영 모두 분류 불가).
    if hard_errors or not closes:
        m.hard_errors = sorted(set(hard_errors)) or ["no_valid_rows"]
        m.is_data_valid = False
        if closes:
            m.current_close = _round(closes[-1])
            m.high_52w = _round(max(highs)); m.low_52w = _round(min(lows))
        _finalize(m)
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

    # --- 분할/조정 의심(운영 차단): 미설명 일일 종가 점프 > 50% ---
    max_jump = 0.0
    for prev, nxt in zip(closes, closes[1:]):
        if prev > 0:
            max_jump = max(max_jump, abs(nxt / prev - 1.0) * 100.0)
    if max_jump > ADJUSTMENT_DAY_JUMP_PCT:
        m.adjustment_warnings.append(
            f"large_one_day_jump:{round(max_jump,1)}%>{ADJUSTMENT_DAY_JUMP_PCT}%"
        )

    # --- 전략-극단(비차단): 대형 52주 range/gain = 강한 주도주 신호(데이터 결함 아님) ---
    if lo > 0 and hi / lo > STRATEGY_EXTREME_RANGE_RATIO:
        m.strategy_extreme_warnings.append(
            f"price_range_ratio_high:{round(hi/lo,2)}>{STRATEGY_EXTREME_RANGE_RATIO}"
        )
    if m.low_52w_gain_pct is not None and m.low_52w_gain_pct > STRATEGY_EXTREME_GAIN_PCT:
        m.strategy_extreme_warnings.append(
            f"low_52w_gain_extreme:{m.low_52w_gain_pct}%>{STRATEGY_EXTREME_GAIN_PCT}%"
        )

    m.is_adjustment_suspect = bool(m.adjustment_warnings)
    m.is_strategy_extreme = bool(m.strategy_extreme_warnings)
    # 비차단 경고도 가시화(연구 참고용 통합 리스트).
    m.data_quality_warnings = m.adjustment_warnings + m.strategy_extreme_warnings

    # --- 후보 분류(매수 신호 아님) ---
    gain, dd = m.low_52w_gain_pct, m.drawdown_from_52w_high_pct
    if gain is not None and dd is not None:
        m.raw_candidate_a = (gain <= CAND_A_MAX_GAIN) and (dd <= CAND_A_MAX_DRAWDOWN)
        m.raw_candidate_b = (gain >= CAND_B_MIN_GAIN) and (dd <= CAND_B_MAX_DRAWDOWN)

    _finalize(m)
    return m


def _finalize(m: LeaderTrendMetrics) -> None:
    """hard_errors/ready/후보/조정의심으로 research·operational bucket + safe 플래그 확정."""
    # 연구 bucket: 경고 무관, 데이터 유효성·충분성·A/B만 반영.
    if not m.is_data_valid:
        research = "invalid_data"
    elif not m.ready_for_52w:
        research = "insufficient_data"
    elif m.raw_candidate_a:
        research = "A"
    elif m.raw_candidate_b:
        research = "B"
    else:
        research = "none"

    # 운영 bucket: 조정 의심은 차단(*_raw_needs_adjusted_review), 전략-극단은 비차단.
    if not m.is_data_valid:
        operational = "invalid_data"
    elif not m.ready_for_52w:
        operational = "insufficient_data"
    elif m.is_adjustment_suspect:
        operational = (
            "A_raw_needs_adjusted_review" if m.raw_candidate_a
            else "B_raw_needs_adjusted_review" if m.raw_candidate_b
            else "none"
        )
    elif m.raw_candidate_a:
        operational = "A"
    elif m.raw_candidate_b:
        operational = "B"
    else:
        operational = "none"

    m.candidate_bucket_research = research
    m.candidate_bucket_operational = operational
    m.candidate_bucket = operational  # 하위 호환 별칭
    # 운영 분류 신뢰 가능: 데이터 유효 + 252봉 + 조정의심 아님. **전략-극단은 막지 않는다.**
    m.operationally_safe_for_classification = (
        m.is_data_valid and m.ready_for_52w and not m.is_adjustment_suspect
    )


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
            _BUCKET_RANK.get(m.candidate_bucket_operational, 99),
            m.drawdown_from_52w_high_pct if m.drawdown_from_52w_high_pct is not None else float("inf"),
            -(m.low_52w_gain_pct if m.low_52w_gain_pct is not None else float("-inf")),
            m.symbol,
        ))
        return results
