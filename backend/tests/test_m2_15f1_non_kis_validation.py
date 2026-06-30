"""M2.15F-1 — non-KIS 독립 52주 검증 하네스 테스트.

읽기 전용 · DB write 0 · KIS/broker/http 0 · SignalLog/Trade/Order/CandidateEvent 0.
synthetic reference dict + 시드한 market_data로 분류 로직 검증.
"""
from datetime import datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.db.session import get_db
from app.main import app
from app.services.leader_trend_validation_service import LeaderTrendValidationService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


async def _seed(session: AsyncSession, symbol: str, highs_lows_close: list[tuple[float, float, float]]) -> None:
    base = datetime(2025, 1, 1, tzinfo=KST)
    rows = [
        {"s": symbol, "ts": base + timedelta(days=i), "o": c, "h": h, "l": lo, "c": c, "v": 1000}
        for i, (h, lo, c) in enumerate(highs_lows_close)
    ]
    await session.execute(text(
        "insert into market_data (symbol_code,timeframe,ts,open,high,low,close,volume) "
        "values (:s,'1d',:ts,:o,:h,:l,:c,:v)"
    ), rows)
    await session.flush()


def _ref(symbols: list[dict]) -> dict:
    return {"source_name": "synthetic", "source_note": "test", "as_of_date": "2026-06-30",
            "timeframe": "1d", "symbols": symbols}


# --- service classification ---------------------------------------------------
async def test_classification_statuses(db_session: AsyncSession):
    # MATCH: db hi=110 lo=90 close=100 vs ref same → matched (0%)
    await _seed(db_session, "AAA", [(110, 90, 100), (105, 95, 100)])
    # MINOR: db hi=110 vs ref 109 (~0.9%) → minor_diff
    await _seed(db_session, "BBB", [(110, 90, 100)])
    # MAJOR: db hi=110 vs ref 100 (10%) → major_diff
    await _seed(db_session, "CCC", [(110, 90, 100)])
    # placeholder ref
    await _seed(db_session, "DDD", [(110, 90, 100)])
    # EEE: db rows exist but no reference entry → missing_reference_data
    await _seed(db_session, "EEE", [(110, 90, 100)])

    ref = _ref([
        {"symbol": "AAA", "reference_close": 100, "high_52w": 110, "low_52w": 90, "source_url_or_note": "real"},
        {"symbol": "BBB", "reference_close": 100, "high_52w": 109, "low_52w": 90, "source_url_or_note": "real"},
        {"symbol": "CCC", "reference_close": 100, "high_52w": 100, "low_52w": 90, "source_url_or_note": "real"},
        {"symbol": "DDD", "reference_close": 0, "high_52w": 0, "low_52w": 0, "source_url_or_note": "manual placeholder"},
        # FFF: reference exists but no DB rows → missing_db_data
        {"symbol": "FFF", "reference_close": 100, "high_52w": 110, "low_52w": 90, "source_url_or_note": "real"},
    ])
    svc = LeaderTrendValidationService(db_session, reference=ref)
    rep = await svc.validate(["AAA", "BBB", "CCC", "DDD", "EEE"])
    st = {r.symbol: r.validation_status for r in rep.results}
    assert st["AAA"] == "matched"
    assert st["BBB"] == "minor_diff"
    assert st["CCC"] == "major_diff"
    assert st["DDD"] == "placeholder_reference"
    assert st["EEE"] == "missing_reference_data"

    rep2 = await svc.validate(["FFF"])
    assert rep2.results[0].validation_status == "missing_db_data"


async def test_max_5_symbols_cap_in_service(db_session: AsyncSession):
    svc = LeaderTrendValidationService(db_session, reference=_ref([]))
    rep = await svc.validate(["A", "B", "C", "D", "E", "F", "G"])
    assert len(rep.symbols) == 5


def test_service_module_no_external_or_trading_paths():
    import app.services.leader_trend_validation_service as mod
    src = open(mod.__file__, encoding="utf-8").read()
    for forbidden in ("httpx", "requests", "place_order", "get_daily_candles", "get_current_price",
                      "KISRealBrokerClient", "KISPaperBrokerClient", "TradeService", "OrderService",
                      "SignalLog(", "Trade(", "Order(", "CandidateEvent(", "upsert", ".commit(",
                      "session.add", "scheduler"):
        assert forbidden not in src, f"unexpected token: {forbidden}"


# --- API ----------------------------------------------------------------------
async def _client(session):
    app.dependency_overrides[get_db] = _override_get_db(session)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_api_default_pilot_filled_naver(db_session: AsyncSession):
    # M2.15F-3E: runtime default snapshot은 이제 네이버 값으로 채워짐.
    # 005930 DB(작은 합성값) vs 네이버 ref(323000) → major_diff. 미시드 종목은 missing_db_data.
    await _seed(db_session, "005930", [(110, 90, 100)])
    client = await _client(db_session)
    try:
        r = await client.get("/api/v1/leader-trend/validation/non-kis-52w")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert body["research_only"] is True
    assert body["not_buy_signal"] is True
    assert body["read_only"] is True
    assert body["external_reference_auto_fetch"] is False
    assert body["universe_scope"] == "pilot_5"
    assert body["total_symbols_checked"] == 5
    assert "not a buy signal" in body["safety_warning"].lower()
    assert "non-kis" in body["provenance_warning"].lower()
    assert body["reference_source_name"] == "네이버증권"
    by = {r_["symbol"]: r_["validation_status"] for r_ in body["results"]}
    assert by["005930"] == "major_diff"            # 작은 DB값 vs 실제 네이버 ref → 큰 차이
    assert by["000660"] == "missing_db_data"        # 미시드
    assert body["summary"]["placeholder_reference"] == 0


async def test_api_wildcard_and_cap_rejected(db_session: AsyncSession):
    client = await _client(db_session)
    try:
        w = await client.get("/api/v1/leader-trend/validation/non-kis-52w?symbols=all")
        cap = await client.get("/api/v1/leader-trend/validation/non-kis-52w?symbols=005930,000660,035420,005380,051910,005490")
    finally:
        app.dependency_overrides.clear()
    assert w.status_code == 400
    assert cap.status_code == 400


async def test_api_does_not_write_db(db_session: AsyncSession):
    await _seed(db_session, "005930", [(110, 90, 100)])
    md_before = (await db_session.execute(text("select count(*) from market_data"))).scalar()
    sig_before = (await db_session.execute(text("select count(*) from signal_logs"))).scalar()
    tr_before = (await db_session.execute(text("select count(*) from trades"))).scalar()
    client = await _client(db_session)
    try:
        await client.get("/api/v1/leader-trend/validation/non-kis-52w")
    finally:
        app.dependency_overrides.clear()
    assert (await db_session.execute(text("select count(*) from market_data"))).scalar() == md_before
    assert (await db_session.execute(text("select count(*) from signal_logs"))).scalar() == sig_before
    assert (await db_session.execute(text("select count(*) from trades"))).scalar() == tr_before
