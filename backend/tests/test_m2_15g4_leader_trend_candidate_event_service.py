"""M2.15G-4 — LeaderTrendCandidateEventService create policy 테스트 (test DB).

success(matched/minor_diff/explained_major_diff+note) · reject(정책 위반) · duplicate · 안전(주문/신호/스케줄러 0).
"""
from dataclasses import replace
from datetime import date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.services.leader_trend_candidate_event_service import (
    LeaderTrendCandidateEventCreateInput,
    LeaderTrendCandidateEventDuplicateError,
    LeaderTrendCandidateEventService,
    LeaderTrendCandidateEventValidationError,
)


def _input(**over) -> LeaderTrendCandidateEventCreateInput:
    base = LeaderTrendCandidateEventCreateInput(
        symbol="005930", detected_at=datetime(2026, 6, 30, tzinfo=KST),
        reference_date=date(2026, 6, 29), timeframe="1d", universe_scope="pilot_5",
        scanner_name="leader_trend", scanner_version="v1", candidate_bucket="B",
        is_operational_candidate=True, strategy_extreme=True, current_price=323000,
        low_52w=57600, high_52w=380000, low_52w_gain_pct=460.76,
        drawdown_from_52w_high_pct=15.0, window_basis="last_252_trading_rows",
        data_source="local_market_data", validation_source="naver_manual",
        validation_status="minor_diff", validation_report_path="docs/x.md",
        research_only=True, not_buy_signal=True,
    )
    return replace(base, **over)


# --- success ------------------------------------------------------------------
async def test_create_minor_diff(db_session: AsyncSession):
    svc = LeaderTrendCandidateEventService(db_session)
    ev = await svc.create_research_event(_input(validation_status="minor_diff"))
    assert ev.id is not None and ev.research_only is True and ev.not_buy_signal is True


async def test_create_matched(db_session: AsyncSession):
    svc = LeaderTrendCandidateEventService(db_session)
    ev = await svc.create_research_event(_input(validation_status="matched", window_basis="calendar_52_weeks"))
    assert ev.id is not None


async def test_create_explained_major_diff_with_note(db_session: AsyncSession):
    svc = LeaderTrendCandidateEventService(db_session)
    ev = await svc.create_research_event(_input(
        validation_status="explained_major_diff", source_basis_note="window basis difference (F-3F)"))
    assert ev.id is not None


# --- rejections ---------------------------------------------------------------
@pytest.mark.parametrize("over,msg", [
    ({"validation_status": "unresolved_major_diff"}, "validation_status"),
    ({"validation_status": "not_validated"}, "validation_status"),
    ({"validation_status": "explained_major_diff", "source_basis_note": None}, "source_basis_note"),
    ({"research_only": False}, "research_only"),
    ({"not_buy_signal": False}, "not_buy_signal"),
    ({"validation_report_path": None}, "validation_report_path"),
    ({"scanner_version": ""}, "scanner_version"),
    ({"universe_scope": "us_all"}, "universe_scope"),
    ({"universe_scope": "all"}, "wildcard"),
    ({"scanner_name": "other"}, "scanner_name"),
    ({"data_source": "kis_live"}, "data_source"),
    ({"timeframe": "5m"}, "timeframe"),
    ({"candidate_bucket": "C"}, "candidate_bucket"),
    ({"window_basis": "weird"}, "window_basis"),
    ({"window_basis": ""}, "window_basis"),
])
async def test_rejections(db_session: AsyncSession, over, msg):
    svc = LeaderTrendCandidateEventService(db_session)
    with pytest.raises(LeaderTrendCandidateEventValidationError) as e:
        await svc.create_research_event(_input(**over))
    assert msg in str(e.value)


async def test_reject_duplicate(db_session: AsyncSession):
    svc = LeaderTrendCandidateEventService(db_session)
    await svc.create_research_event(_input())
    with pytest.raises(LeaderTrendCandidateEventDuplicateError):
        await svc.create_research_event(_input())  # 같은 unique key


# --- safety -------------------------------------------------------------------
async def test_create_writes_only_leader_trend_table(db_session: AsyncSession):
    async def c(t):
        return (await db_session.execute(text(f"select count(*) from {t}"))).scalar()
    trades_before, sig_before = await c("trades"), await c("signal_logs")
    ltce_before = await c("leader_trend_candidate_events")
    svc = LeaderTrendCandidateEventService(db_session)
    await svc.create_research_event(_input())
    assert await c("trades") == trades_before
    assert await c("signal_logs") == sig_before
    assert await c("leader_trend_candidate_events") == ltce_before + 1


def test_service_module_no_trading_or_external():
    import app.services.leader_trend_candidate_event_service as mod
    src = open(mod.__file__, encoding="utf-8").read()
    # 실제 코드 패턴만 차단(docstring prose 제외).
    for forbidden in ("import httpx", "import requests", "place_order(", "get_current_price(",
                      "get_daily_candles(", ".add_job(", "TradeService", "OrderService",
                      "StrategyRunnerService", "SignalLog(", "Trade(", "Order(",
                      "APIRouter", "FastAPI", "broker_client"):
        assert forbidden not in src, f"unexpected token: {forbidden}"


def test_only_create_api_no_read_or_mutate_routes():
    # G-5 이후: candidate-events는 create-only POST 하나. read/list/update/delete/bulk 금지.
    from pathlib import Path
    route = (Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "leader_trend.py").read_text(encoding="utf-8")
    assert "/candidate-events/research-only" in route
    for forbidden in ('@router.get("/candidate-events"', '@router.get("/candidate-events/{',
                      '@router.put("/candidate-events', '@router.patch("/candidate-events',
                      '@router.delete("/candidate-events', "/candidate-events/bulk",
                      "/candidate-events/save-all"):
        assert forbidden not in route
