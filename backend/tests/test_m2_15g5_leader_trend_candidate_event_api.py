"""M2.15G-5 — explicit manual LeaderTrendCandidateEvent create API 테스트.

POST /api/v1/leader-trend/candidate-events/research-only — service 통해서만 생성 · 매수 신호 아님 ·
validation→400 / duplicate→409 · 주문/거래/신호 0 · read/list/update/delete route 없음.
"""
from datetime import date, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.db.session import get_db
from app.main import app

URL = "/api/v1/leader-trend/candidate-events/research-only"


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


def _body(**over) -> dict:
    b = {
        "symbol": "005930", "detected_at": datetime(2026, 6, 30, tzinfo=KST).isoformat(),
        "reference_date": "2026-06-29", "timeframe": "1d", "universe_scope": "pilot_5",
        "scanner_name": "leader_trend", "scanner_version": "v1", "candidate_bucket": "B",
        "is_operational_candidate": True, "strategy_extreme": True, "current_price": 323000,
        "low_52w": 57600, "high_52w": 380000, "low_52w_gain_pct": 460.76,
        "drawdown_from_52w_high_pct": 15.0, "window_basis": "last_252_trading_rows",
        "data_source": "local_market_data", "validation_source": "naver_manual",
        "validation_status": "minor_diff", "validation_report_path": "docs/x.md",
        "research_only": True, "not_buy_signal": True,
    }
    b.update(over)
    return b


async def _client(session):
    app.dependency_overrides[get_db] = _override_get_db(session)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --- success ------------------------------------------------------------------
async def test_create_minor_diff_success(db_session: AsyncSession):
    client = await _client(db_session)
    try:
        r = await client.post(URL, json=_body())
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 201
    b = r.json()
    assert b["id"] > 0
    assert b["research_only"] is True and b["not_buy_signal"] is True
    assert "not be connected to trading" in b["safety_warning"]
    assert "not a buy signal" in b["not_buy_signal_warning"].lower()
    assert b["candidate_bucket"] == "B" and b["validation_status"] == "minor_diff"


async def test_create_matched_success(db_session: AsyncSession):
    client = await _client(db_session)
    try:
        r = await client.post(URL, json=_body(validation_status="matched",
                                              window_basis="calendar_52_weeks"))
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 201


async def test_create_explained_major_diff_with_note(db_session: AsyncSession):
    client = await _client(db_session)
    try:
        r = await client.post(URL, json=_body(validation_status="explained_major_diff",
                                              source_basis_note="window basis (F-3F)"))
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 201


# --- rejections (400) ---------------------------------------------------------
@pytest.mark.parametrize("over", [
    {"validation_status": "unresolved_major_diff"},
    {"validation_status": "not_validated"},
    {"validation_status": "explained_major_diff"},  # source_basis_note 없음
    {"research_only": False},
    {"not_buy_signal": False},
    {"validation_report_path": None},
    {"universe_scope": "us_all"},
    {"universe_scope": "all"},
    {"scanner_name": "other"},
    {"data_source": "kis_live"},
    {"timeframe": "5m"},
])
async def test_create_validation_rejected_400(db_session: AsyncSession, over):
    client = await _client(db_session)
    try:
        r = await client.post(URL, json=_body(**over))
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 400


async def test_create_duplicate_409(db_session: AsyncSession):
    client = await _client(db_session)
    try:
        first = await client.post(URL, json=_body())
        dup = await client.post(URL, json=_body())
    finally:
        app.dependency_overrides.clear()
    assert first.status_code == 201
    assert dup.status_code == 409


# --- safety -------------------------------------------------------------------
async def test_create_no_trade_signal_order_side_effect(db_session: AsyncSession):
    async def c(t):
        return (await db_session.execute(text(f"select count(*) from {t}"))).scalar()
    tr, sig = await c("trades"), await c("signal_logs")
    ltce = await c("leader_trend_candidate_events")
    client = await _client(db_session)
    try:
        await client.post(URL, json=_body())
    finally:
        app.dependency_overrides.clear()
    assert await c("trades") == tr
    assert await c("signal_logs") == sig
    assert await c("leader_trend_candidate_events") == ltce + 1


def test_no_forbidden_candidate_event_routes():
    route = (Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "leader_trend.py").read_text(encoding="utf-8")
    for forbidden in ('@router.get("/candidate-events"', '@router.get("/candidate-events/{',
                      '@router.put("/candidate-events', '@router.patch("/candidate-events',
                      '@router.delete("/candidate-events', "/candidate-events/bulk",
                      "/candidate-events/save-all"):
        assert forbidden not in route
    # 새 API/서비스에 외부/주문/스케줄러 실코드 토큰 없음
    for forbidden in ("import httpx", "place_order(", "get_current_price(", ".add_job(",
                      "TradeService", "OrderService", "StrategyRunnerService"):
        assert forbidden not in route
