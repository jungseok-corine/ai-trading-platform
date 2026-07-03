"""C-7.2: 전략 카탈로그 + 입학시험.

안전 검증: 모든 카탈로그 스펙이 DSL 검증 통과, 기준 미달은 제안 미생성,
통과분도 pending(승인은 사람) + auto_trade=false.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.market_data import MarketData
from app.services.strategy_catalog import (
    CATALOG,
    EXAM_SYMBOLS,
    StrategyCatalogService,
    passes_admission,
)
from app.trading.strategy.rule_dsl import required_bars, validate_rule_spec


def test_all_catalog_specs_valid():
    assert len(CATALOG) >= 5
    for entry in CATALOG:
        validate_rule_spec(entry["spec"])  # no raise
        assert entry["regime_fit"] in ("trend", "range")
        assert "source" in entry["spec"]
        assert required_bars(entry["spec"]) < 100  # 일봉 1년(252봉)으로 평가 가능


def test_admission_gate():
    ok = {"trade_count": 8, "return_pct": 20.0, "max_drawdown_pct": 15.0, "buy_hold_return_pct": 30.0}
    assert passes_admission(ok)[0] is True
    assert passes_admission({**ok, "trade_count": 2})[0] is False
    assert passes_admission({**ok, "return_pct": -1.0})[0] is False
    assert passes_admission({**ok, "max_drawdown_pct": 40.0})[0] is False
    # 강세 보유(+100%) 대비 너무 낮은 수익(+10%) → 탈락
    assert passes_admission({**ok, "return_pct": 10.0, "buy_hold_return_pct": 100.0})[0] is False
    # 백테스트 실패
    assert passes_admission({"symbols_used": 0})[0] is False


async def _seed_trending_daily(session: AsyncSession, symbol: str, days: int = 300) -> None:
    """추세 시장 일봉 시드 — turtle/momentum류가 입학할 수 있는 환경."""
    base = datetime(2025, 8, 1, 6, 0, tzinfo=timezone.utc)
    price = 10_000
    for i in range(days):
        # 완만한 상승 + 주기적 조정 (거래가 여러 번 발생하도록)
        drift = 40 if (i // 30) % 3 != 2 else -35
        price = max(1_000, price + drift)
        session.add(
            MarketData(
                symbol_code=symbol, timeframe="1d", ts=base + timedelta(days=i),
                open=Decimal(price - 10), high=Decimal(price + 60),
                low=Decimal(price - 60), close=Decimal(price), volume=100_000 + (i % 7) * 30_000,
            )
        )
    await session.commit()


@pytest.mark.asyncio
async def test_seed_creates_pending_proposals_only_for_passing(db_session: AsyncSession):
    for sym in EXAM_SYMBOLS:
        await _seed_trending_daily(db_session, sym)

    results = await StrategyCatalogService(db_session).seed_and_validate(exam_days=365)
    assert len(results) == len(CATALOG)

    passed = [r for r in results if r["passed"]]
    failed = [r for r in results if not r["passed"]]
    # 합성 추세 시장에서 최소 1개는 통과, 전부 통과는 아니어야 기준이 살아있는 것
    assert passed, f"입학 통과 0 — 기준 과빡 또는 엔진 문제: {[r['reason'] for r in results]}"
    for r in passed:
        assert r["proposal_id"] is not None
    for r in failed:
        assert "proposal_id" not in r

    # 생성된 제안 안전성: pending + auto_trade=false + rule_spec 포함
    from app.domain.models.strategy_proposal import StrategyProposal
    from sqlalchemy import select

    proposals = (
        (await db_session.execute(
            select(StrategyProposal).where(StrategyProposal.source == "catalog")
        )).scalars().all()
    )
    assert len(proposals) == len(passed)
    for p in proposals:
        assert p.status.value == "pending"
        assert p.suggested_parameters["auto_trade_enabled"] is False
        assert p.suggested_parameters["strategy_type"] == "rule_based"
        validate_rule_spec(p.suggested_parameters["rule_spec"])


@pytest.mark.asyncio
async def test_seed_idempotent_dedup(db_session: AsyncSession):
    for sym in EXAM_SYMBOLS:
        await _seed_trending_daily(db_session, sym)
    svc = StrategyCatalogService(db_session)
    first = await svc.seed_and_validate(exam_days=365)
    second = await svc.seed_and_validate(exam_days=365)
    for r in second:
        if r["passed"]:
            assert r["deduped"] is True  # 중복 제안 안 만듦
