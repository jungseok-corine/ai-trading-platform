"""M2.15F-3A — DB-side 52주 snapshot export 테스트.

읽기 전용 · DB write 0 · KIS/broker/http 0 · SignalLog/Trade/Order/CandidateEvent 0.
synthetic market_data(1d)로 row_count/날짜/52주 high·low·close/gain·dd/bucket 계산 검증.
"""
from datetime import datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.db.session import get_db
from app.main import app
from app.services.leader_trend_validation_service import db_52w_snapshot


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


async def _seed(session: AsyncSession, symbol: str, hloc: list[tuple[float, float, float]]) -> None:
    base = datetime(2025, 1, 1, tzinfo=KST)
    rows = [
        {"s": symbol, "ts": base + timedelta(days=i), "o": c, "h": h, "l": lo, "c": c, "v": 1000}
        for i, (h, lo, c) in enumerate(hloc)
    ]
    await session.execute(text(
        "insert into market_data (symbol_code,timeframe,ts,open,high,low,close,volume) "
        "values (:s,'1d',:ts,:o,:h,:l,:c,:v)"
    ), rows)
    await session.flush()


async def _client(session):
    app.dependency_overrides[get_db] = _override_get_db(session)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --- service computation ------------------------------------------------------
async def test_snapshot_computes_fields(db_session: AsyncSession):
    # day0 high=120 (peak), day1 low=80 (trough), day2 close=100 (last)
    await _seed(db_session, "AAA", [(120, 100, 110), (115, 80, 90), (105, 95, 100)])
    rep = await db_52w_snapshot(db_session, ["AAA"])
    r = rep.results[0]
    assert r.row_count == 3
    assert r.first_date == "20250101" and r.last_date == "20250103"
    assert r.db_reference_close == 100 and r.db_reference_close_date == "20250103"
    assert r.db_high_52w == 120 and r.db_high_52w_date == "20250101"
    assert r.db_low_52w == 80 and r.db_low_52w_date == "20250102"
    assert r.low_52w_gain_pct == 25.0          # 100/80-1
    assert r.drawdown_from_52w_high_pct == round((120 - 100) / 120 * 100, 2)
    assert r.candidate_bucket_if_any in {"A", "B", "A_raw_needs_adjusted_review",
                                         "B_raw_needs_adjusted_review", "none",
                                         "insufficient_data", "invalid_data"}
    assert r.data_quality_note == "computed_from_existing_market_data_only"


async def test_snapshot_missing_db_data(db_session: AsyncSession):
    rep = await db_52w_snapshot(db_session, ["ZZZ"])
    r = rep.results[0]
    assert r.row_count == 0 and r.data_quality_note == "missing_db_data"
    assert r.candidate_bucket_if_any is None


async def test_snapshot_caps_at_5(db_session: AsyncSession):
    rep = await db_52w_snapshot(db_session, ["A", "B", "C", "D", "E", "F"])
    assert len(rep.results) == 5


# --- API ----------------------------------------------------------------------
async def test_api_default_pilot_and_flags(db_session: AsyncSession):
    await _seed(db_session, "005930", [(120, 100, 110), (105, 95, 100)])
    client = await _client(db_session)
    try:
        r = await client.get("/api/v1/leader-trend/validation/db-52w-snapshot")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    b = r.json()
    assert b["research_only"] is True
    assert b["not_buy_signal"] is True
    assert b["read_only"] is True
    assert b["external_reference_auto_fetch"] is False
    assert b["kis_call_used"] is False
    assert b["db_write_performed"] is False
    assert b["universe_scope"] == "pilot_5"
    assert b["timeframe"] == "1d"
    assert b["total_symbols_checked"] == 5
    assert "not a buy signal" in b["safety_warning"].lower()
    assert "no external or kis fetch" in b["provenance_warning"].lower()
    by = {x["symbol"]: x for x in b["results"]}
    assert by["005930"]["row_count"] == 2
    assert by["000660"]["data_quality_note"] == "missing_db_data"  # 미시드


async def test_api_wildcard_and_cap_rejected(db_session: AsyncSession):
    client = await _client(db_session)
    try:
        w = await client.get("/api/v1/leader-trend/validation/db-52w-snapshot?symbols=all")
        cap = await client.get("/api/v1/leader-trend/validation/db-52w-snapshot?symbols=005930,000660,035420,005380,051910,005490")
    finally:
        app.dependency_overrides.clear()
    assert w.status_code == 400 and cap.status_code == 400


async def test_api_no_db_write(db_session: AsyncSession):
    await _seed(db_session, "005930", [(120, 100, 110)])
    md = (await db_session.execute(text("select count(*) from market_data"))).scalar()
    sig = (await db_session.execute(text("select count(*) from signal_logs"))).scalar()
    tr = (await db_session.execute(text("select count(*) from trades"))).scalar()
    client = await _client(db_session)
    try:
        await client.get("/api/v1/leader-trend/validation/db-52w-snapshot")
    finally:
        app.dependency_overrides.clear()
    assert (await db_session.execute(text("select count(*) from market_data"))).scalar() == md
    assert (await db_session.execute(text("select count(*) from signal_logs"))).scalar() == sig
    assert (await db_session.execute(text("select count(*) from trades"))).scalar() == tr
