"""M2.15C-4 — 계층화 경고 모델 테스트 (결정적 합성 일봉, DB/네트워크 미사용).

hard_errors / adjustment_warnings / strategy_extreme_warnings 분리 검증.
- 전략-극단(range/gain) = 비차단(운영 분류 가능).
- 조정 의심(일일점프>50%) = 운영 차단(*_raw_needs_adjusted_review).
- hard 결함 = invalid_data.
읽기 전용 · SignalLog/Trade/Order 0 · broker/provider 미호출 · market_data 미변경.
"""
from datetime import datetime, timedelta

import pytest

from app.common.timezone import KST
from app.services.leader_trend_scanner import LeaderTrendScanner, compute_metrics


class FakeCandle:
    def __init__(self, ts, o, h, l, c, v):
        self.ts, self.open, self.high, self.low, self.close, self.volume = ts, o, h, l, c, v


def _ts(i):
    return datetime(2025, 1, 1, tzinfo=KST) + timedelta(days=i)


def _rows(per_row):
    return [FakeCandle(_ts(i), *r) for i, r in enumerate(per_row)]


def _const(n, price=100, vol=1000):
    return _rows([(price, price, price, price, vol)] * n)


def _climb(n, start, end):
    """start→end 점진 상승(>50% 일일점프 없음)."""
    rows = []
    for i in range(n):
        base = start * (end / start) ** (i / (n - 1))
        rows.append((base, base * 1.01, base * 0.99, base, 1000))
    return _rows(rows)


# --- 1. clean Candidate A → research A / operational A / safe ------------------
def test_clean_candidate_a():
    m = compute_metrics("A", _const(252, 100))
    assert m.raw_candidate_a
    assert m.candidate_bucket_research == "A" and m.candidate_bucket_operational == "A"
    assert m.candidate_bucket == "A"  # 하위 호환 별칭
    assert m.is_data_valid and not m.is_adjustment_suspect and not m.is_strategy_extreme
    assert m.operationally_safe_for_classification


# --- 2. clean Candidate B (gain<500, ratio<4) → operational B / safe -----------
def test_clean_candidate_b():
    # 100→350 (gain 250, ratio 3.6) 점진 → 경고 없음
    m = compute_metrics("B", _climb(252, 100, 350))
    assert m.raw_candidate_b and not m.is_strategy_extreme and not m.is_adjustment_suspect
    assert m.candidate_bucket_research == "B" and m.candidate_bucket_operational == "B"
    assert m.operationally_safe_for_classification
    assert m.strategy_extreme_warnings == []


# --- 3. Candidate B + range_ratio>4 only → operational B, extreme, safe --------
def test_candidate_b_range_ratio_only_non_blocking():
    # 100→490 (ratio>4, gain ~390<500) → range만 전략-극단
    m = compute_metrics("RB", _climb(252, 100, 490))
    assert m.raw_candidate_b
    assert any("price_range_ratio_high" in w for w in m.strategy_extreme_warnings)
    assert not any("gain_extreme" in w for w in m.strategy_extreme_warnings)
    assert m.is_strategy_extreme and not m.is_adjustment_suspect
    assert m.candidate_bucket_operational == "B"
    assert m.operationally_safe_for_classification


# --- 4. Candidate B + gain>500 → operational B, extreme, safe ------------------
def test_candidate_b_gain_extreme_non_blocking():
    m = compute_metrics("GB", _climb(252, 100, 800))  # gain ~700>500, ratio>4
    assert m.raw_candidate_b
    assert any("low_52w_gain_extreme" in w for w in m.strategy_extreme_warnings)
    assert m.is_strategy_extreme and not m.is_adjustment_suspect
    assert m.candidate_bucket_operational == "B"
    assert m.operationally_safe_for_classification


# --- 5. extreme but clean sustained data → operational B, warning, safe --------
def test_candidate_b_extreme_clean_sustained():
    m = compute_metrics("EB", _climb(252, 100, 1000))  # gain ~900, ratio ~10
    assert m.raw_candidate_b and m.is_strategy_extreme
    # 점진 상승이라 일일점프<50% → 조정 의심 아님
    assert not m.is_adjustment_suspect
    assert m.candidate_bucket_operational == "B"
    assert m.candidate_bucket_research == "B"
    assert m.operationally_safe_for_classification


# --- 6. Candidate B + one-day jump>50 → review, adjustment_suspect, not safe ---
def test_candidate_b_day_jump_blocks():
    # 251×100 후 +60% 점프(160) → 조정 의심. gain 60? no — 마지막만 160이면 gain (160/100-1)=60 <200 → not B.
    # B를 유지하려면 저점100, 큰 상승 + 막판 점프. 100→300 점진(gain~200) 후 마지막 +60% 점프.
    rows = []
    for i in range(251):
        base = 100 * (300 / 100) ** (i / 250)
        rows.append((base, base * 1.01, base * 0.99, base, 1000))
    last_prev = rows[-1][3]
    jumped = last_prev * 1.6  # +60% 일일 점프
    rows.append((last_prev, jumped, last_prev, jumped, 1000))
    m = compute_metrics("JB", _rows(rows))
    assert m.raw_candidate_b
    assert any("large_one_day_jump" in w for w in m.adjustment_warnings)
    assert m.is_adjustment_suspect
    assert m.candidate_bucket_research == "B"                       # 연구는 B
    assert m.candidate_bucket_operational == "B_raw_needs_adjusted_review"  # 운영 차단
    assert not m.operationally_safe_for_classification


# --- 7. insufficient ----------------------------------------------------------
def test_insufficient():
    m = compute_metrics("S", _const(251))
    assert m.candidate_bucket_research == "insufficient_data"
    assert m.candidate_bucket_operational == "insufficient_data"
    assert not m.operationally_safe_for_classification


# --- 8~12. hard invalid → invalid_data (research & operational) ----------------
@pytest.mark.parametrize("mutate,token", [
    (lambda r: r.__setitem__(10, FakeCandle(_ts(10), 0, 0, 0, 0, 100)), "nonpositive_price"),
    (lambda r: r.__setitem__(5, FakeCandle(_ts(5), 100, 90, 110, 100, 100)), "high_lt_low"),
    (lambda r: r.__setitem__(7, FakeCandle(_ts(7), 100, 105, 95, 130, 100)), "close_outside_low_high"),
    (lambda r: r.__setitem__(3, FakeCandle(_ts(2), 100, 100, 100, 100, 100)), "duplicate_date"),
])
def test_hard_invalid(mutate, token):
    rows = _const(252)
    mutate(rows)
    m = compute_metrics("I", rows)
    assert not m.is_data_valid
    assert any(token in w for w in m.hard_errors)
    assert m.candidate_bucket_research == "invalid_data"
    assert m.candidate_bucket_operational == "invalid_data"
    assert not m.operationally_safe_for_classification


def test_hard_invalid_null_ohlcv():
    rows = _const(252)
    rows[8] = FakeCandle(_ts(8), None, 100, 100, 100, 100)  # null → 파싱불가
    m = compute_metrics("N", rows)
    assert not m.is_data_valid
    assert any("null_or_unparsable" in w for w in m.hard_errors)
    assert m.candidate_bucket_operational == "invalid_data"


# --- 13. no candidate stays none ----------------------------------------------
def test_no_candidate_none():
    # 점진 100→300(고점) 후 점진 300→200(현재): gain100 dd33 → none, 일일점프<50%(깨끗)
    up = [100 * (300 / 100) ** (i / 125) for i in range(126)]
    down = [300 * (200 / 300) ** (i / 125) for i in range(1, 127)]
    seq = up + down
    m = compute_metrics("N", _rows([(p, p * 1.005, p * 0.995, p, 1000) for p in seq]))
    assert m.candidate_bucket_research == "none" and m.candidate_bucket_operational == "none"
    assert not m.is_adjustment_suspect
    # 데이터 무결·조정의심 아님 → 운영 분류는 신뢰 가능(none이 신뢰됨)
    assert m.operationally_safe_for_classification


# --- 14. MA/recent_high/volume 정확 (회귀) ------------------------------------
def test_moving_averages_regression():
    rows = [(100, 100, 100, 100, 1000)] * 232 + [(200, 200, 200, 200, 2000)] * 20
    m = compute_metrics("M", _rows(rows))
    assert m.ma20 == 200
    assert m.ma50 == round((30 * 100 + 20 * 200) / 50, 1)
    assert m.recent_20d_high == 200 and m.volume_20d_avg == 2000


# --- 15/16. 스캐너 결정적 정렬 + 명시 심볼만 ----------------------------------
@pytest.mark.asyncio
async def test_scanner_orders_and_explicit_symbols(monkeypatch):
    loaded = []
    data = {
        "A1": _const(252, 100),          # operational A
        "B1": _climb(252, 100, 350),     # operational B (clean)
        "NONE1": _rows([(100, 100, 100, 100, 1)] * 200 + [(300, 300, 300, 300, 1)]
                       + [(200, 200, 200, 200, 1)] * 51),
    }

    async def fake_load(self, symbol):
        loaded.append(symbol)
        return data.get(symbol, [])

    monkeypatch.setattr(LeaderTrendScanner, "_load_daily", fake_load, raising=True)
    res = await LeaderTrendScanner(session=None).scan(["NONE1", "B1", "A1"])  # type: ignore[arg-type]
    assert loaded == ["NONE1", "B1", "A1"]
    assert [m.candidate_bucket_operational for m in res] == ["A", "B", "none"]


# --- 17~22. 스캐너/모듈에 trading/mutation/provider 경로 없음(구조적) ----------
def test_scanner_module_no_trading_paths():
    import app.services.leader_trend_scanner as mod
    src = open(mod.__file__, encoding="utf-8").read()
    for forbidden in ("place_order", "TradeService", "OrderService", "SignalLog(",
                      "Trade(", "Order(", "upsert", "session.add", ".commit(",
                      "get_daily_candles", "KISPaperBrokerClient", "scheduler"):
        assert forbidden not in src, f"unexpected token: {forbidden}"
