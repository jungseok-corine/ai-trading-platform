"""C-6.22 종목-전략 적합성 매칭 (D-31 실행) — 추세성 분류 → breakout/rsi 배정."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.core.config import Settings
from app.db.session import get_db
from app.domain.models.market_data import MarketData
from app.main import app
from app.trading.analysis.symbol_trendiness import (
    RANGE,
    TREND,
    UNKNOWN,
    classify_trendiness,
    is_compatible,
)

_BASE_TS = datetime(2026, 3, 2, 0, 0, tzinfo=KST)


@dataclass
class _Candle:
    ts: datetime
    close: float


def _candles(closes: list[float]) -> list[_Candle]:
    return [_Candle(ts=_BASE_TS + timedelta(days=i), close=c) for i, c in enumerate(closes)]


# --------------------------------------------------------------------------- #
# 순수 분류기
# --------------------------------------------------------------------------- #


def test_classify_uptrend() -> None:
    # 60일 100→150 상승: ma20>ma50, close>ma50, 수익률 50% ≥ 10%
    closes = [100 + i * (50 / 59) for i in range(60)]
    r = classify_trendiness(_candles(closes))
    assert r.classification == TREND
    assert r.return_lookback_pct is not None and r.return_lookback_pct > 10


def test_classify_downtrend_is_range() -> None:
    # 하락 종목은 rsi(방어) 대상 → range
    closes = [150 - i * (50 / 59) for i in range(60)]
    r = classify_trendiness(_candles(closes))
    assert r.classification == RANGE


def test_classify_sideways_is_range() -> None:
    closes = [100 + (1 if i % 2 else -1) for i in range(60)]
    r = classify_trendiness(_candles(closes))
    assert r.classification == RANGE


def test_classify_insufficient_is_unknown() -> None:
    r = classify_trendiness(_candles([100.0] * 30))
    assert r.classification == UNKNOWN
    assert any("insufficient" in reason for reason in r.reasons)


def test_is_compatible_mapping() -> None:
    assert is_compatible("breakout_high", TREND) is True
    assert is_compatible("breakout_high", RANGE) is False   # 횡보 breakout 금지 (D-31)
    assert is_compatible("rsi_reversion", RANGE) is True
    assert is_compatible("rsi_reversion", TREND) is False
    assert is_compatible("breakout_high", UNKNOWN) is True  # 분류 불가 → 필터 없음
    assert is_compatible("some_future_type", RANGE) is True  # 미등재 타입 → 필터 없음


# --------------------------------------------------------------------------- #
# 배정 통합 (AssignmentService)
# --------------------------------------------------------------------------- #


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


def _enable_matching(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(_env_file=None, assignment_fitness_matching_enabled=True),
    )


async def _make_candidate(client: AsyncClient) -> tuple[int, int]:
    rule_id = (
        await client.post("/api/v1/scanner-rules", json={"name": "vol spike", "market": "KR"})
    ).json()["id"]
    version_id = (
        await client.post(
            f"/api/v1/scanner-rules/{rule_id}/versions",
            json={
                "conditions": [{"type": "volume_spike", "params": {"multiplier": 2.0}}],
                "status": "testing",
            },
        )
    ).json()["id"]
    scan = await client.post(
        f"/api/v1/scanner-rules/{rule_id}/versions/{version_id}/scan",
        json={"symbol_facts": {"005930": {"volume_ratio": 2.5}}},
    )
    return rule_id, scan.json()["candidates"][0]["id"]


async def _seed_daily(session: AsyncSession, closes: list[float], symbol: str = "005930") -> None:
    for i, c in enumerate(closes):
        px = Decimal(str(round(c, 2)))
        session.add(MarketData(
            symbol_code=symbol, timeframe="1d", ts=_BASE_TS + timedelta(days=i),
            open=px, high=px + 1, low=px - 1, close=px, volume=1000,
        ))
    await session.commit()


async def _two_rules(client: AsyncClient) -> None:
    """breakout(우선순위 높음) + rsi(낮음) fallback 규칙 2개."""
    await client.post("/api/v1/assignment-rules", json={
        "name": "breakout", "strategy_type": "breakout_high", "market": "KR", "priority": 10,
    })
    await client.post("/api/v1/assignment-rules", json={
        "name": "rsi", "strategy_type": "rsi_reversion", "market": "KR", "priority": 5,
    })


async def test_matching_off_keeps_priority_order(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, candidate_id = await _make_candidate(client)
            await _seed_daily(db_session, [150 - i * 0.8 for i in range(60)])  # 하락
            await _two_rules(client)

            log = (await client.post(f"/api/v1/candidates/{candidate_id}/assign")).json()
            # 매칭 off(기본) → 기존 동작: 우선순위 최상위 breakout, 추세성 미기록
            assert log["strategy_type"] == "breakout_high"
            assert log["symbol_trendiness"] is None
    finally:
        app.dependency_overrides.clear()


async def test_matching_on_range_symbol_gets_rsi(db_session: AsyncSession, monkeypatch) -> None:
    _enable_matching(monkeypatch)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, candidate_id = await _make_candidate(client)
            await _seed_daily(db_session, [150 - i * 0.8 for i in range(60)])  # 하락 → range
            await _two_rules(client)

            log = (await client.post(f"/api/v1/candidates/{candidate_id}/assign")).json()
            # 하락/횡보 종목엔 breakout(우선순위 높아도) 대신 rsi_reversion (D-31)
            assert log["strategy_type"] == "rsi_reversion"
            assert log["symbol_trendiness"] == RANGE
    finally:
        app.dependency_overrides.clear()


async def test_matching_on_trend_symbol_gets_breakout(db_session: AsyncSession, monkeypatch) -> None:
    _enable_matching(monkeypatch)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, candidate_id = await _make_candidate(client)
            await _seed_daily(db_session, [100 + i * 0.9 for i in range(60)])  # 상승 → trend
            await _two_rules(client)

            log = (await client.post(f"/api/v1/candidates/{candidate_id}/assign")).json()
            assert log["strategy_type"] == "breakout_high"
            assert log["symbol_trendiness"] == TREND
    finally:
        app.dependency_overrides.clear()


async def test_matching_on_no_daily_data_falls_back(db_session: AsyncSession, monkeypatch) -> None:
    _enable_matching(monkeypatch)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, candidate_id = await _make_candidate(client)  # 일봉 없음
            await _two_rules(client)

            log = (await client.post(f"/api/v1/candidates/{candidate_id}/assign")).json()
            # unknown → 필터 없음 → 기존 우선순위대로 breakout
            assert log["strategy_type"] == "breakout_high"
            assert log["symbol_trendiness"] == UNKNOWN
    finally:
        app.dependency_overrides.clear()


async def test_matching_on_no_compatible_rule_falls_back_visibly(
    db_session: AsyncSession, monkeypatch
) -> None:
    _enable_matching(monkeypatch)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, candidate_id = await _make_candidate(client)
            await _seed_daily(db_session, [150 - i * 0.8 for i in range(60)])  # range
            # breakout 규칙만 존재 → 호환 규칙 없음
            await client.post("/api/v1/assignment-rules", json={
                "name": "breakout-only", "strategy_type": "breakout_high",
                "market": "KR", "priority": 10,
            })

            log = (await client.post(f"/api/v1/candidates/{candidate_id}/assign")).json()
            # 배정은 유지(연구 로그 손실 방지)하되 부적합이 보이게 range 기록
            assert log["strategy_type"] == "breakout_high"
            assert log["symbol_trendiness"] == RANGE
    finally:
        app.dependency_overrides.clear()
