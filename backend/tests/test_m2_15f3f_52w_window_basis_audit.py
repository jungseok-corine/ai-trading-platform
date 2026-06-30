"""M2.15F-3F — 52주 window basis audit 테스트.

last_252_trading_rows vs calendar_52_weeks를 합성 데이터로 검증. 읽기 전용 · DB write 0 · KIS/http 0 ·
SignalLog/Trade/Order/CandidateEvent 0.
"""
from datetime import datetime, timedelta
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.db.session import get_db
from app.main import app
from app.services.leader_trend_validation_service import window_basis_audit

AUDIT_DOC = (Path(__file__).resolve().parents[2] / "docs" / "data-validation"
             / "52w-window-basis-audit-2026-06-29.md")
REPORT = (Path(__file__).resolve().parents[2] / "docs" / "data-validation"
          / "non-kis-52w-validation-report-2026-06-29-naver.md")


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


async def _seed_window_case(session: AsyncSession, symbol: str) -> None:
    """last_date=2026-06-29 기준 ~390일 시계열. 가장 오래된(>364일) 봉에 최저가 100, 그 뒤 calendar 내 최저 120."""
    last = datetime(2026, 6, 29, tzinfo=KST)
    rows = []
    # day -389 (calendar window 밖): low 100 (252-row가 잡는 더 오래된 저점)
    rows.append({"ts": last - timedelta(days=389), "h": 130, "l": 100, "c": 125})
    # day -380 (밖): low 110
    rows.append({"ts": last - timedelta(days=380), "h": 132, "l": 110, "c": 128})
    # calendar window 내(<=364): low 120 (calendar 최저)
    for i, d in enumerate(range(360, 0, -2)):  # 여러 봉
        rows.append({"ts": last - timedelta(days=d), "h": 200 + i, "l": 120 + i, "c": 150 + i})
    rows.append({"ts": last, "h": 210, "l": 205, "c": 208})  # 최신 close
    payload = [{"s": symbol, "ts": r["ts"], "o": r["c"], "h": r["h"], "l": r["l"], "c": r["c"], "v": 1000}
               for r in rows]
    await session.execute(text(
        "insert into market_data (symbol_code,timeframe,ts,open,high,low,close,volume) "
        "values (:s,'1d',:ts,:o,:h,:l,:c,:v)"), payload)
    await session.flush()


async def test_window_basis_low_differs(db_session: AsyncSession):
    await _seed_window_case(db_session, "AAA")
    # Naver low = 120 (calendar 최저와 일치) → explainable true
    ref = {"symbols": [{"symbol": "AAA", "reference_close": 208, "high_52w": 210,
                        "low_52w": 120, "source_url_or_note": "naver"}]}
    rows = await window_basis_audit(db_session, ref, ["AAA"])
    r = rows[0]
    assert r.last_252_trading_rows.low_52w == 100      # 오래된 저점 포함
    assert r.calendar_52_weeks.low_52w == 120          # calendar는 100 제외
    assert r.calendar_52_weeks.first_date > r.last_252_trading_rows.first_date
    assert abs(r.low_252_vs_naver_diff_pct) > 2.0      # 252는 Naver와 차이 큼
    assert abs(r.low_calendar_vs_naver_diff_pct) <= 2.0
    assert r.naver_major_diff_explainable_by_window_basis == "true"


async def test_window_basis_unknown_when_placeholder(db_session: AsyncSession):
    await _seed_window_case(db_session, "BBB")
    ref = {"symbols": [{"symbol": "BBB", "reference_close": 0, "high_52w": 0,
                        "low_52w": 0, "source_url_or_note": "placeholder"}]}
    rows = await window_basis_audit(db_session, ref, ["BBB"])
    assert rows[0].naver_major_diff_explainable_by_window_basis == "unknown"


# --- API ----------------------------------------------------------------------
async def _client(session):
    app.dependency_overrides[get_db] = _override_get_db(session)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_api_flags_and_scope(db_session: AsyncSession):
    await _seed_window_case(db_session, "005930")
    client = await _client(db_session)
    try:
        r = await client.get("/api/v1/leader-trend/validation/52w-window-basis-audit")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    b = r.json()
    assert b["research_only"] is True and b["not_buy_signal"] is True and b["read_only"] is True
    assert b["external_reference_auto_fetch"] is False
    assert b["kis_call_used"] is False and b["db_write_performed"] is False
    assert b["candidate_event_allowed"] is False
    assert b["universe_scope"] == "pilot_5"
    assert b["total_symbols_checked"] == 5
    # 각 결과에 두 basis 포함
    assert all("last_252_trading_rows" in x and "calendar_52_weeks" in x for x in b["results"])


async def test_api_wildcard_and_cap_rejected(db_session: AsyncSession):
    client = await _client(db_session)
    try:
        w = await client.get("/api/v1/leader-trend/validation/52w-window-basis-audit?symbols=all")
        cap = await client.get("/api/v1/leader-trend/validation/52w-window-basis-audit?symbols=a,b,c,d,e,f")
    finally:
        app.dependency_overrides.clear()
    assert w.status_code == 400 and cap.status_code == 400


async def test_api_no_db_write(db_session: AsyncSession):
    await _seed_window_case(db_session, "005930")
    md = (await db_session.execute(text("select count(*) from market_data"))).scalar()
    sig = (await db_session.execute(text("select count(*) from signal_logs"))).scalar()
    tr = (await db_session.execute(text("select count(*) from trades"))).scalar()
    client = await _client(db_session)
    try:
        await client.get("/api/v1/leader-trend/validation/52w-window-basis-audit")
    finally:
        app.dependency_overrides.clear()
    assert (await db_session.execute(text("select count(*) from market_data"))).scalar() == md
    assert (await db_session.execute(text("select count(*) from signal_logs"))).scalar() == sig
    assert (await db_session.execute(text("select count(*) from trades"))).scalar() == tr


def test_docs_and_report_reference_audit():
    assert AUDIT_DOC.exists()
    atext = AUDIT_DOC.read_text(encoding="utf-8")
    assert "CandidateEvent allowed: no" in atext
    assert "calendar_52_weeks" in atext
    rtext = REPORT.read_text(encoding="utf-8")
    assert "52w-window-basis-audit-2026-06-29.md" in rtext  # report links to audit
