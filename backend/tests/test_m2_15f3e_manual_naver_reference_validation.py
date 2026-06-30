"""M2.15F-3E — 네이버증권 manual reference 입력 후 non-KIS 검증.

manual snapshot이 네이버 값으로 채워졌고, dev DB(실 데이터)와 비교 시 005930/051910이 major_diff(low_52w)임을 확인.
읽기 전용 · DB write 0 · CandidateEvent/SignalLog/Trade/Order 0 · KIS/http 0.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.db.session import get_db
from app.main import app
from app.services import leader_trend_validation_service as svc_mod

REPORT = (Path(__file__).resolve().parents[2] / "docs" / "data-validation"
          / "non-kis-52w-validation-report-2026-06-29-naver.md")

# 각 종목 DB baseline (high_52w, low_52w, latest_close) — dev DB 값 재현용.
_DB_BASELINE = {
    "005930": (380000, 57600, 323000),
    "000660": (3002000, 242000, 2610000),
    "035420": (308500, 190300, 205500),
    "005380": (787000, 200500, 499500),
    "051910": (437500, 200500, 308000),
}


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


async def _seed_baseline(session: AsyncSession, symbol: str, hi: float, lo: float, close: float) -> None:
    base = datetime(2025, 1, 1, tzinfo=KST)
    # row0=max high, row1=min low, row2(last)=latest close
    triples = [(hi, hi * 0.97, hi * 0.98), (lo * 1.02, lo, lo * 1.01), (close * 1.005, close * 0.995, close)]
    rows = [{"s": symbol, "ts": base + timedelta(days=i), "o": c, "h": h, "l": l, "c": c, "v": 1000}
            for i, (h, l, c) in enumerate(triples)]
    await session.execute(text(
        "insert into market_data (symbol_code,timeframe,ts,open,high,low,close,volume) "
        "values (:s,'1d',:ts,:o,:h,:l,:c,:v)"), rows)
    await session.flush()


def test_manual_snapshot_filled_with_naver():
    d = json.loads(svc_mod._DEFAULT_REFERENCE_PATH.read_text(encoding="utf-8"))
    assert d["source_name"] == "네이버증권"
    assert d["as_of_date"] == "2026-06-29"
    syms = {s["symbol"]: s for s in d["symbols"]}
    # reference 값이 더 이상 전부 0이 아님
    assert any(s["reference_close"] != 0 for s in syms.values())
    assert syms["005930"]["reference_close"] == 323000
    assert syms["005930"]["reference_close_date"] == "2026-06-29"
    assert syms["005930"]["source_name"] == "네이버증권"
    # db_* baseline은 reference로 덮어쓰이지 않음(독립성)
    assert syms["005930"]["db_low_52w"] == 57600 and syms["005930"]["low_52w"] == 59800


async def test_validation_endpoint_classifies_naver_diffs(db_session: AsyncSession):
    # dev DB baseline 재현 후 네이버 ref와 비교. 005930/051910 = major_diff(low_52w).
    for sym, (hi, lo, close) in _DB_BASELINE.items():
        await _seed_baseline(db_session, sym, hi, lo, close)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            b = (await c.get("/api/v1/leader-trend/validation/non-kis-52w")).json()
    finally:
        app.dependency_overrides.clear()
    assert b["reference_source_name"] == "네이버증권"
    assert b["summary"]["placeholder_reference"] == 0
    by = {r["symbol"]: r["validation_status"] for r in b["results"]}
    # 005930 또는 051910 중 최소 하나 이상 major_diff (둘 다 low_52w major)
    assert "major_diff" in {by["005930"], by["051910"]}
    assert by["005930"] == "major_diff" and by["051910"] == "major_diff"
    assert b["summary"]["major_diff"] >= 2


def test_report_exists_and_blocks_candidate_event():
    assert REPORT.exists()
    text = REPORT.read_text(encoding="utf-8")
    assert "SAFE TO PROCEED TO CANDIDATE EVENT DESIGN: no" in text
    assert "네이버증권" in text


def test_validation_service_module_no_trading_or_external():
    src = open(svc_mod.__file__, encoding="utf-8").read()
    for forbidden in ("httpx", "requests", "place_order", "get_current_price", "CandidateEvent(",
                      "SignalLog(", "Trade(", "Order(", "upsert", ".commit(", "scheduler"):
        assert forbidden not in src, f"unexpected token: {forbidden}"
