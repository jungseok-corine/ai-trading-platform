"""M2.15D-3B — Leader Trend 후보 read-only 노출 API 테스트.

합성 일봉을 test DB market_data(1d)에 시드한 뒤 엔드포인트 검증. 후보는 매수 신호 아님 · 영속화/주문/신호 0.
"""
from datetime import datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.db.session import get_db
from app.main import app


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


async def _seed_daily(session: AsyncSession, symbol: str, closes: list[float]) -> None:
    """closes 시퀀스를 1d market_data로 시드(o=h*0.99 근사, h=close*1.005...)."""
    base = datetime(2025, 1, 1, tzinfo=KST)
    rows = []
    for i, c in enumerate(closes):
        ts = base + timedelta(days=i)
        rows.append({"s": symbol, "ts": ts, "o": c, "h": c * 1.005, "l": c * 0.995, "c": c, "v": 1000})
    await session.execute(text(
        "insert into market_data (symbol_code,timeframe,ts,open,high,low,close,volume) "
        "values (:s,'1d',:ts,:o,:h,:l,:c,:v)"
    ), rows)
    await session.flush()


def _climb(n, start, end):
    return [start * (end / start) ** (i / (n - 1)) for i in range(n)]


async def _client(session):
    app.dependency_overrides[get_db] = _override_get_db(session)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_candidates_default_pilot_and_warnings(db_session: AsyncSession):
    # B 후보(전략-극단): 100→1000 점진 → operational B, strategy_extreme
    await _seed_daily(db_session, "005930", _climb(252, 100, 1000))
    # none: 점진 100→300 후 200 (gain100 dd33)
    up = _climb(126, 100, 300); down = [300 * (200 / 300) ** (i / 125) for i in range(1, 127)]
    await _seed_daily(db_session, "035420", up + down)

    client = await _client(db_session)
    try:
        r = await client.get("/api/v1/leader-trend/candidates")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert body["research_only"] is True
    assert body["not_buy_signal"] is True
    assert "non-KIS independence unconfirmed" in body["provenance_warning"]
    assert "NOT buy signals" in body["safety_warning"]
    assert body["universe_scope"] == "pilot_5"
    assert body["total_symbols_scanned"] == 5  # 기본 5종(미시드 3종은 insufficient_data)
    syms = {x["symbol"] for x in body["results"]}
    assert syms == {"005930", "000660", "035420", "005380", "051910"}
    by = {x["symbol"]: x for x in body["results"]}
    assert by["005930"]["candidate_bucket_operational"] == "B"
    assert by["005930"]["is_strategy_extreme"] is True
    assert by["005930"]["strategy_extreme_warnings"]
    assert by["035420"]["candidate_bucket_operational"] == "none"
    # 미시드 종목은 insufficient_data(데이터 없음)
    assert by["000660"]["candidate_bucket_operational"] == "insufficient_data"
    # operational 후보 카운트 = 005930(B)
    assert body["total_operational_candidates"] == 1
    assert {c["symbol"] for c in body["candidates"]} == {"005930"}
    # "buy signal"이 긍정 라벨로 쓰이지 않음 — bucket/필드에 buy/order/trade 없음
    for x in body["results"]:
        assert "buy" not in x["candidate_bucket_operational"].lower()


async def test_explicit_symbols_capped(db_session: AsyncSession):
    client = await _client(db_session)
    try:
        r = await client.get("/api/v1/leader-trend/candidates?symbols=005930,000660,035420,005380,051910,005490")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 400
    assert "max" in r.json()["detail"].lower()


async def test_wildcard_rejected(db_session: AsyncSession):
    client = await _client(db_session)
    try:
        r = await client.get("/api/v1/leader-trend/candidates?symbols=all")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 400


async def test_explicit_single_symbol_ok(db_session: AsyncSession):
    await _seed_daily(db_session, "005930", _climb(252, 100, 1000))
    client = await _client(db_session)
    try:
        r = await client.get("/api/v1/leader-trend/candidates?symbols=005930")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert body["universe_scope"] == "explicit"
    assert body["total_symbols_scanned"] == 1
    assert body["results"][0]["candidate_bucket_operational"] == "B"


async def test_endpoint_does_not_write_db(db_session: AsyncSession):
    await _seed_daily(db_session, "005930", _climb(252, 100, 1000))
    before = (await db_session.execute(text("select count(*) from market_data where timeframe='1d'"))).scalar()
    sig_before = (await db_session.execute(text("select count(*) from signal_logs"))).scalar()
    tr_before = (await db_session.execute(text("select count(*) from trades"))).scalar()
    client = await _client(db_session)
    try:
        await client.get("/api/v1/leader-trend/candidates")
    finally:
        app.dependency_overrides.clear()
    after = (await db_session.execute(text("select count(*) from market_data where timeframe='1d'"))).scalar()
    assert after == before
    assert (await db_session.execute(text("select count(*) from signal_logs"))).scalar() == sig_before
    assert (await db_session.execute(text("select count(*) from trades"))).scalar() == tr_before


def test_route_module_no_trading_paths():
    import app.api.v1.leader_trend as mod
    src = open(mod.__file__, encoding="utf-8").read()
    for forbidden in ("place_order", "get_daily_candles", "KISPaperBrokerClient",
                      "KISRealBrokerClient", "TradeService", "OrderService", "SignalLog(",
                      "Trade(", "Order(", "scheduler", "upsert", ".commit("):
        assert forbidden not in src, f"unexpected token: {forbidden}"
