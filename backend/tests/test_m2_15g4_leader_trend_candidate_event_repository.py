"""M2.15G-4 — LeaderTrendCandidateEventRepository 테스트 (test DB insert만 허용).

create/get_by_id/list_by_reference_date/exists_by_unique_key · forbidden 메서드 부재 · FK 없음 ·
기존 candidate_events 미참조.
"""
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.models.leader_trend_candidate_event import LeaderTrendCandidateEvent
from app.domain.repositories.leader_trend_candidate_event import (
    LeaderTrendCandidateEventRepository,
)


def _event(symbol="005930", window_basis="last_252_trading_rows") -> LeaderTrendCandidateEvent:
    return LeaderTrendCandidateEvent(
        symbol=symbol, detected_at=datetime(2026, 6, 30, tzinfo=KST),
        reference_date=date(2026, 6, 29), timeframe="1d", universe_scope="pilot_5",
        scanner_name="leader_trend", scanner_version="v1", candidate_bucket="B",
        is_operational_candidate=True, strategy_extreme=True, current_price=323000,
        low_52w=57600, high_52w=380000, low_52w_gain_pct=460.76,
        drawdown_from_52w_high_pct=15.0, window_basis=window_basis,
        data_source="local_market_data", validation_source="naver_manual",
        validation_status="minor_diff", validation_report_path="docs/x.md",
        research_only=True, not_buy_signal=True,
    )


async def test_create_and_get_by_id(db_session: AsyncSession):
    repo = LeaderTrendCandidateEventRepository(db_session)
    ev = await repo.create(_event())
    assert ev.id is not None
    got = await repo.get_by_id(ev.id)
    assert got is not None and got.symbol == "005930" and got.research_only is True


async def test_list_by_reference_date(db_session: AsyncSession):
    repo = LeaderTrendCandidateEventRepository(db_session)
    await repo.create(_event("005930", "last_252_trading_rows"))
    await repo.create(_event("000660", "last_252_trading_rows"))
    rows = await repo.list_by_reference_date(date(2026, 6, 29))
    assert {r.symbol for r in rows} >= {"005930", "000660"}
    none_rows = await repo.list_by_reference_date(date(2020, 1, 1))
    assert none_rows == []


async def test_exists_by_unique_key(db_session: AsyncSession):
    repo = LeaderTrendCandidateEventRepository(db_session)
    await repo.create(_event())
    assert await repo.exists_by_unique_key(
        symbol="005930", scanner_name="leader_trend", scanner_version="v1",
        reference_date=date(2026, 6, 29), timeframe="1d",
        window_basis="last_252_trading_rows", universe_scope="pilot_5",
    ) is True
    assert await repo.exists_by_unique_key(
        symbol="005930", scanner_name="leader_trend", scanner_version="v1",
        reference_date=date(2026, 6, 29), timeframe="1d",
        window_basis="calendar_52_weeks", universe_scope="pilot_5",
    ) is False


def test_repository_has_no_forbidden_methods():
    repo_cls = LeaderTrendCandidateEventRepository
    for forbidden in ("upsert", "bulk_create", "update", "delete",
                      "create_from_scheduler", "create_from_strategy_runner",
                      "create_from_ai", "create_from_trade", "create_from_order",
                      "create_from_signal"):
        assert not hasattr(repo_cls, forbidden), f"forbidden method present: {forbidden}"


def test_repository_module_no_external_or_existing_table():
    import app.domain.repositories.leader_trend_candidate_event as mod
    src = open(mod.__file__, encoding="utf-8").read()
    # 실제 코드 패턴만 차단(docstring prose 제외).
    for forbidden in ("import httpx", "import requests", "place_order", "get_daily_candles",
                      "get_current_price", "KISPaperBrokerClient", "KISRealBrokerClient",
                      ".add_job(", "APIRouter", "FastAPI"):
        assert forbidden not in src, f"unexpected token: {forbidden}"
    # 기존 candidate_events(C-2.24) 모델/테이블 미참조.
    assert "from app.domain.models.candidate_event import" not in src
    assert 'select(MarketData)' not in src  # 다른 테이블 직접 조작 안 함(자기 모델만)


def test_model_has_no_foreign_keys():
    assert len(LeaderTrendCandidateEvent.__table__.foreign_keys) == 0
