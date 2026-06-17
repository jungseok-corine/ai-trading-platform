"""Market Data 조회/summary API 통합 테스트."""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.market_data import MarketData
from app.main import app

KST = ZoneInfo("Asia/Seoul")


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


def _ts(date: str, time: str) -> datetime:
    """YYYYMMDD + HHMMSS → KST datetime."""
    return datetime.strptime(f"{date}{time}", "%Y%m%d%H%M%S").replace(tzinfo=KST)


async def _insert_candles(session: AsyncSession, rows: list[dict]) -> None:
    for row in rows:
        session.add(MarketData(**row))
    await session.flush()


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _db_override(db_session: AsyncSession):
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    yield
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _candle_row(
    symbol_code: str = "005930",
    timeframe: str = "1m",
    date: str = "20260610",
    time: str = "090000",
    close: int = 100,
) -> dict:
    price = Decimal(close)
    return {
        "symbol_code": symbol_code,
        "timeframe": timeframe,
        "ts": _ts(date, time),
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": 1000,
    }


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# GET /api/v1/market-data/{symbol_code} — 목록 조회
# ---------------------------------------------------------------------------


async def test_list_candles_returns_rows(db_session: AsyncSession) -> None:
    await _insert_candles(db_session, [
        _candle_row(time="090000"),
        _candle_row(time="090100"),
        _candle_row(time="090200"),
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/005930")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["symbol_code"] == "005930"
    assert data[0]["timeframe"] == "1m"
    assert "ts" in data[0]
    assert "open" in data[0]
    assert "close" in data[0]
    assert "volume" in data[0]


async def test_list_candles_empty_when_no_data(db_session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/UNKNOWN")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_candles_sorted_ascending(db_session: AsyncSession) -> None:
    await _insert_candles(db_session, [
        _candle_row(time="090200"),
        _candle_row(time="090000"),
        _candle_row(time="090100"),
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/005930")

    timestamps = [row["ts"] for row in resp.json()]
    assert timestamps == sorted(timestamps)


async def test_list_candles_filters_by_timeframe(db_session: AsyncSession) -> None:
    await _insert_candles(db_session, [
        _candle_row(timeframe="1m", time="090000"),
        _candle_row(timeframe="5m", time="090000"),
        _candle_row(timeframe="1m", time="090100"),
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/005930", params={"timeframe": "5m"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["timeframe"] == "5m"


async def test_list_candles_filters_by_start_at(db_session: AsyncSession) -> None:
    await _insert_candles(db_session, [
        _candle_row(time="090000"),
        _candle_row(time="090100"),
        _candle_row(time="090200"),
    ])
    # start_at = 09:01:00 KST → 09:01 이후만 포함
    start = _ts("20260610", "090100").isoformat()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/005930", params={"start_at": start})

    assert resp.status_code == 200
    assert len(resp.json()) == 2  # 090100, 090200


async def test_list_candles_filters_by_end_at(db_session: AsyncSession) -> None:
    await _insert_candles(db_session, [
        _candle_row(time="090000"),
        _candle_row(time="090100"),
        _candle_row(time="090200"),
    ])
    end = _ts("20260610", "090100").isoformat()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/005930", params={"end_at": end})

    assert resp.status_code == 200
    assert len(resp.json()) == 2  # 090000, 090100


async def test_list_candles_limit_applies(db_session: AsyncSession) -> None:
    # 10개 캔들 삽입 (09:00 ~ 09:09)
    rows = [_candle_row(time=f"09{i:02d}00") for i in range(10)]
    await _insert_candles(db_session, rows)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/005930", params={"limit": 3})

    assert resp.status_code == 200
    assert len(resp.json()) == 3


async def test_list_candles_max_limit_enforced(db_session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/005930", params={"limit": 9999})

    assert resp.status_code == 422  # FastAPI Query le=1000 validation


async def test_list_candles_offset_applies(db_session: AsyncSession) -> None:
    # 5개 캔들 삽입 (09:00 ~ 09:04)
    rows = [_candle_row(time=f"09{i:02d}00") for i in range(5)]
    await _insert_candles(db_session, rows)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        all_resp = await client.get("/api/v1/market-data/005930")
        offset_resp = await client.get("/api/v1/market-data/005930", params={"offset": 2})

    all_data = all_resp.json()
    offset_data = offset_resp.json()
    assert offset_data == all_data[2:]


async def test_list_candles_filters_by_symbol_only(db_session: AsyncSession) -> None:
    await _insert_candles(db_session, [
        _candle_row(symbol_code="005930", time="090000"),
        _candle_row(symbol_code="035420", time="090000"),
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/005930")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["symbol_code"] == "005930"


# ---------------------------------------------------------------------------
# GET /api/v1/market-data/{symbol_code}/summary
# ---------------------------------------------------------------------------


async def test_symbol_summary_counts_by_timeframe(db_session: AsyncSession) -> None:
    await _insert_candles(db_session, [
        _candle_row(timeframe="1m", time="090000"),
        _candle_row(timeframe="1m", time="090100"),
        _candle_row(timeframe="5m", time="090000"),
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/005930/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol_code"] == "005930"
    assert data["total_count"] == 3

    by_tf = {r["timeframe"]: r for r in data["by_timeframe"]}
    assert by_tf["1m"]["count"] == 2
    assert by_tf["5m"]["count"] == 1


async def test_symbol_summary_includes_oldest_and_latest_ts(db_session: AsyncSession) -> None:
    await _insert_candles(db_session, [
        _candle_row(time="090000"),
        _candle_row(time="090100"),
        _candle_row(time="090200"),
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/005930/summary")

    data = resp.json()
    assert data["oldest_ts"] is not None
    assert data["latest_ts"] is not None
    assert data["oldest_ts"] < data["latest_ts"]


async def test_symbol_summary_empty_when_no_data(db_session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/NODATA/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol_code"] == "NODATA"
    assert data["total_count"] == 0
    assert data["oldest_ts"] is None
    assert data["latest_ts"] is None
    assert data["by_timeframe"] == []


# ---------------------------------------------------------------------------
# GET /api/v1/market-data/summary — 전체 요약
# ---------------------------------------------------------------------------


async def test_global_summary_lists_all_symbols(db_session: AsyncSession) -> None:
    await _insert_candles(db_session, [
        _candle_row(symbol_code="005930", time="090000"),
        _candle_row(symbol_code="005930", time="090100"),
        _candle_row(symbol_code="035420", time="090000"),
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_symbols"] == 2
    assert data["total_rows"] == 3

    symbols = {s["symbol_code"]: s for s in data["symbols"]}
    assert symbols["005930"]["total_count"] == 2
    assert symbols["035420"]["total_count"] == 1
    assert symbols["005930"]["latest_ts"] is not None


async def test_global_summary_includes_timeframes(db_session: AsyncSession) -> None:
    await _insert_candles(db_session, [
        _candle_row(symbol_code="005930", timeframe="1m", time="090000"),
        _candle_row(symbol_code="005930", timeframe="5m", time="090000"),
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/summary")

    symbols = {s["symbol_code"]: s for s in resp.json()["symbols"]}
    assert set(symbols["005930"]["timeframes"]) == {"1m", "5m"}


async def test_global_summary_empty_db(db_session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_symbols"] == 0
    assert data["total_rows"] == 0
    assert data["symbols"] == []


async def test_global_summary_not_matched_by_symbol_route(db_session: AsyncSession) -> None:
    """GET /market-data/summary 가 /{symbol_code} 라우트에 가로채이지 않는지 확인한다."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/summary")

    # summary 엔드포인트가 올바르게 라우팅되어야 한다 (symbol_code="summary" 로 잡히면 안 됨)
    assert resp.status_code == 200
    assert "total_symbols" in resp.json()
