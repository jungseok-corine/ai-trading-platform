"""M2.15C-1 — Leader Trend 메트릭 계산기/스캐너 테스트 (결정적 합성 일봉, DB/네트워크 미사용).

읽기 전용 계산 검증 · SignalLog/Trade/Order 0 · broker/provider 미호출 · market_data 미변경.
"""
from datetime import datetime, timedelta

import pytest

from app.common.timezone import KST
from app.services.leader_trend_scanner import (
    LeaderTrendScanner,
    compute_metrics,
)


class FakeCandle:
    def __init__(self, ts, o, h, l, c, v):
        self.ts, self.open, self.high, self.low, self.close, self.volume = ts, o, h, l, c, v


def _ts(i: int):
    return (datetime(2025, 1, 1, tzinfo=KST) + timedelta(days=i))


def _rows(per_row):
    """per_row: list of (o,h,l,c,v) → 순차 일자 FakeCandle 리스트."""
    return [FakeCandle(_ts(i), *r) for i, r in enumerate(per_row)]


def _const(n, price=100, vol=1000):
    return _rows([(price, price, price, price, vol)] * n)


# --- 1. 252 정상 계산 + Candidate A(상수 시계열) -------------------------------
def test_252_computes_and_candidate_a():
    m = compute_metrics("X", _const(252, 100, 1000))
    assert m.daily_count == 252 and m.ready_for_52w
    assert m.current_close == 100 and m.high_52w == 100 and m.low_52w == 100
    assert m.low_52w_gain_pct == 0 and m.drawdown_from_52w_high_pct == 0
    assert m.ma20 == 100 and m.ma50 == 100 and m.recent_20d_high == 100
    assert m.volume_20d_avg == 1000
    assert m.raw_candidate_a and not m.raw_candidate_b
    assert m.candidate_bucket == "A"
    assert m.operationally_safe_for_classification and not m.data_quality_warnings


# --- 3. Candidate B(점진 상승, 경고 없음) -------------------------------------
def test_candidate_b_no_warning():
    # 100 → 350 점진(일일 ~0.5%, >50% 점프 없음), 마지막 close=350, high≈360 → gain 250, dd 작음, ratio<4
    rows = []
    for i in range(252):
        base = 100 * (350 / 100) ** (i / 251)
        rows.append((base, base * 1.01, base * 0.995, base, 1000))
    m = compute_metrics("B", _rows(rows))
    assert m.low_52w_gain_pct >= 200 and m.drawdown_from_52w_high_pct <= 20
    assert m.raw_candidate_b and not m.raw_candidate_a
    assert m.candidate_bucket == "B"
    assert m.operationally_safe_for_classification
    assert m.data_quality_warnings == []


# --- 4. no-candidate -----------------------------------------------------------
def test_no_candidate():
    # gain=100 (B 아님, <200), dd≈33 (A 아님, >10) → none
    rows = [(100, 100, 100, 100, 1000)] * 200  # low_52w=100
    rows += [(300, 300, 300, 300, 1000)] * 1    # high_52w=300
    rows += [(200, 200, 200, 200, 1000)] * 51   # current=200 → gain100 dd33
    m = compute_metrics("N", _rows(rows))
    assert m.low_52w_gain_pct == 100 and round(m.drawdown_from_52w_high_pct) == 33
    assert not m.raw_candidate_a and not m.raw_candidate_b
    assert m.candidate_bucket == "none"


# --- 5. insufficient_data ------------------------------------------------------
def test_insufficient_data():
    m = compute_metrics("S", _const(251))
    assert not m.ready_for_52w and m.has_120
    assert m.candidate_bucket == "insufficient_data"


# --- 6. invalid: nonpositive price --------------------------------------------
def test_invalid_nonpositive_price():
    rows = _const(252)
    rows[10] = FakeCandle(_ts(10), 0, 0, 0, 0, 100)
    m = compute_metrics("I", rows)
    assert m.candidate_bucket == "invalid_data"
    assert any("nonpositive" in w for w in m.data_quality_warnings)
    assert not m.operationally_safe_for_classification


# --- 7. invalid: high < low ----------------------------------------------------
def test_invalid_high_lt_low():
    rows = _const(252)
    rows[5] = FakeCandle(_ts(5), 100, 90, 110, 100, 100)  # high<low, close outside
    m = compute_metrics("H", rows)
    assert m.candidate_bucket == "invalid_data"
    assert any("high_lt_low" in w for w in m.data_quality_warnings)


# --- 8. duplicate date ---------------------------------------------------------
def test_invalid_duplicate_date():
    rows = _const(252)
    rows[3] = FakeCandle(_ts(2), 100, 100, 100, 100, 100)  # 같은 날짜 중복
    m = compute_metrics("D", rows)
    assert m.candidate_bucket == "invalid_data"
    assert any("duplicate_date" in w for w in m.data_quality_warnings)


# --- 9/10/11. MA20/MA50/recent_20d_high/volume_20d_avg ------------------------
def test_moving_averages_and_recent_high():
    # 232×100 + 20×200; high=close
    rows = [(100, 100, 100, 100, 1000)] * 232 + [(200, 200, 200, 200, 2000)] * 20
    m = compute_metrics("M", _rows(rows))
    assert m.ma20 == 200                       # 최근 20개 모두 200
    assert m.ma50 == round((30 * 100 + 20 * 200) / 50, 1)  # 140.0
    assert m.recent_20d_high == 200
    assert m.volume_20d_avg == 2000


# --- 12. range ratio 경고 → B에 review 라벨 ------------------------------------
def test_warn_price_range_ratio():
    # low_52w=100, high_52w=500 (ratio 5>4), 점진 상승로 gain 큼 → 경고 + 후보
    rows = []
    for i in range(252):
        base = 100 * (480 / 100) ** (i / 251)
        rows.append((base, base * 1.02, base * 0.99, base, 1000))
    m = compute_metrics("R", _rows(rows))
    assert any("price_range_ratio_high" in w for w in m.data_quality_warnings)
    assert not m.operationally_safe_for_classification
    assert m.candidate_bucket.endswith("_raw_needs_adjusted_review")


# --- 13. 극단 gain 경고 --------------------------------------------------------
def test_warn_extreme_gain():
    # 100 → 700 (gain 600>500)
    rows = []
    for i in range(252):
        base = 100 * (700 / 100) ** (i / 251)
        rows.append((base, base * 1.01, base * 0.995, base, 1000))
    m = compute_metrics("G", _rows(rows))
    assert any("low_52w_gain_extreme" in w for w in m.data_quality_warnings)
    assert m.candidate_bucket.endswith("_raw_needs_adjusted_review")


# --- 14. 큰 일일 점프 경고 -----------------------------------------------------
def test_warn_large_one_day_jump():
    rows = _const(252, 100)
    # 마지막 봉 직전 종가 대비 +120% 점프(분할/조정 의심)
    rows[251] = FakeCandle(_ts(251), 100, 220, 100, 220, 1000)
    m = compute_metrics("J", rows)
    assert any("large_one_day_jump" in w for w in m.data_quality_warnings)
    assert not m.operationally_safe_for_classification


# --- 15. raw 후보 + 경고 → *_raw_needs_adjusted_review --------------------------
def test_candidate_a_with_warning_becomes_review():
    # 251×100 후 마지막 종가 +51% 점프(151)로 유지 → gain51/dd0(A 범위)이지만 일일 점프 경고
    rows = _const(251, 100)
    rows.append(FakeCandle(_ts(251), 100, 151, 100, 151, 1000))  # close 100→151 = +51%
    m = compute_metrics("AW", rows)
    assert m.low_52w_gain_pct == 51 and m.drawdown_from_52w_high_pct == 0
    assert m.raw_candidate_a  # gain<=200 & dd<=10
    assert any("large_one_day_jump" in w for w in m.data_quality_warnings)
    assert m.candidate_bucket == "A_raw_needs_adjusted_review"
    assert not m.operationally_safe_for_classification


# --- 16/22. 스캐너: 명시 심볼만 읽고 결정적 정렬 -------------------------------
@pytest.mark.asyncio
async def test_scanner_reads_only_given_symbols_and_orders(monkeypatch):
    loaded = []

    fake_data = {
        "A1": _const(252, 100),                       # bucket A (dd0)
        "NONE1": _rows([(100, 100, 100, 100, 1)] * 200 + [(300, 300, 300, 300, 1)]
                       + [(200, 200, 200, 200, 1)] * 51),  # none
        "INS": _const(100),                            # insufficient
    }

    async def fake_load(self, symbol):
        loaded.append(symbol)
        return fake_data.get(symbol, [])

    monkeypatch.setattr(LeaderTrendScanner, "_load_daily", fake_load, raising=True)
    scanner = LeaderTrendScanner(session=None)  # type: ignore[arg-type]
    res = await scanner.scan(["NONE1", "INS", "A1"])

    assert loaded == ["NONE1", "INS", "A1"]            # 명시 심볼만, 순서대로 읽음
    buckets = [m.candidate_bucket for m in res]
    # 정렬: A < none < insufficient_data
    assert buckets == ["A", "none", "insufficient_data"]


# --- 17~21. 스캐너는 신호/거래/주문/브로커/뮤테이션 경로가 없다(구조적) ---------
def test_scanner_module_has_no_trading_paths():
    import app.services.leader_trend_scanner as mod
    src = open(mod.__file__, encoding="utf-8").read()
    for forbidden in ("place_order", "TradeService", "OrderService", "SignalLog(",
                      "Trade(", "Order(", "upsert", "session.add", "commit(",
                      "get_daily_candles", "KISPaperBrokerClient"):
        assert forbidden not in src, f"unexpected trading/mutation token: {forbidden}"
