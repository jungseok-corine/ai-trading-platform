"""C-3.1 AI 비용·사용량 집계 테스트 (순수 단가 + 서비스 집계)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.ai_analysis import AiAnalysisRun, AiModelResponse
from app.domain.models.enums import (
    AnalysisRunMode,
    AnalysisRunStatus,
    AnalysisRunType,
    AnalysisTargetType,
)
from app.services.ai_cost_service import AiCostService
from app.trading.analysis.model_pricing import estimate_cost, lookup_price


# --- 순수 단가 -------------------------------------------------------------
def test_lookup_prefers_longest_match() -> None:
    # gpt-5.4-mini가 gpt-5.4보다 우선되어야 한다
    assert lookup_price("gpt-5.4-mini") == (0.15, 0.60)
    assert lookup_price("gpt-5.4") == (2.5, 10.0)
    assert lookup_price("claude-sonnet-4-6") == (3.0, 15.0)


def test_estimate_cost_and_unpriced() -> None:
    # 1M input @5 + 1M output @15 = 20.0
    cost, priced = estimate_cost("gpt-5.5", 1_000_000, 1_000_000)
    assert priced and cost == 20.0
    # 미상 모델 → 0, priced False
    cost, priced = estimate_cost("some-unknown-model", 1000, 1000)
    assert cost == 0.0 and priced is False
    # 토큰 None → 0
    assert estimate_cost("fake", None, None) == (0.0, True)


# --- 서비스 집계 -----------------------------------------------------------
async def _make_run(session: AsyncSession) -> AiAnalysisRun:
    run = AiAnalysisRun(
        analysis_type=AnalysisRunType.STRATEGY_PERFORMANCE,
        target_type=AnalysisTargetType.STRATEGY_VERSION,
        target_id=1,
        mode=AnalysisRunMode.SINGLE,
        prompt_type="improvement",
        provider="openai",
        model="gpt-5.4",
        status=AnalysisRunStatus.SUCCEEDED,
    )
    session.add(run)
    await session.flush()
    return run


async def test_summary_aggregates_by_model_and_day(db_session: AsyncSession) -> None:
    run = await _make_run(db_session)
    now = datetime.now(timezone.utc)
    # gpt-5.4: 1M in / 1M out = 2.5 + 10 = 12.5
    r1 = AiModelResponse(
        run_id=run.id, provider="openai", model="gpt-5.4", role="primary_analysis",
        prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000,
    )
    # claude-haiku: 1M in / 0 = 1.0
    r2 = AiModelResponse(
        run_id=run.id, provider="anthropic", model="claude-haiku-4-5", role="synthesis",
        prompt_tokens=1_000_000, completion_tokens=0, total_tokens=1_000_000,
    )
    # 미상 모델
    r3 = AiModelResponse(
        run_id=run.id, provider="x", model="mystery-9", role="primary_analysis",
        prompt_tokens=500, completion_tokens=500, total_tokens=1000,
    )
    db_session.add_all([r1, r2, r3])
    await db_session.flush()

    out = await AiCostService(db_session).summary(days=30)
    assert out["total"]["responses"] == 3
    assert out["total"]["est_cost_usd"] == 13.5  # 12.5 + 1.0 + 0
    assert "mystery-9" in out["unpriced_models"]
    # 비용 내림차순 → gpt-5.4가 첫번째
    assert out["by_model"][0]["model"] == "gpt-5.4"
    assert out["by_model"][0]["est_cost_usd"] == 12.5
    # 오늘 일자 집계 존재
    today = now.date().isoformat()
    assert any(d["date"] == today for d in out["by_day"])


class _FakeSettings:
    def __init__(self, budget, threshold=80.0):
        self.ai_cost_monthly_budget_usd = budget
        self.ai_cost_alert_threshold_pct = threshold


async def test_budget_disabled_by_default(db_session: AsyncSession) -> None:
    out = await AiCostService(db_session).summary(days=30)
    assert out["budget"]["status"] == "disabled"
    assert out["budget"]["used_pct"] is None


async def test_budget_statuses(db_session: AsyncSession, monkeypatch) -> None:
    run = await _make_run(db_session)
    # gpt-5.4 1M input @2.5 = $2.5
    db_session.add(AiModelResponse(
        run_id=run.id, provider="openai", model="gpt-5.4", role="primary_analysis",
        prompt_tokens=1_000_000, completion_tokens=0, total_tokens=1_000_000,
    ))
    await db_session.flush()

    # 예산 $10 → 25% → ok
    monkeypatch.setattr("app.services.ai_cost_service.get_settings",
                        lambda: _FakeSettings(10.0))
    out = await AiCostService(db_session).summary(days=30)
    assert out["budget"]["status"] == "ok" and out["budget"]["used_pct"] == 25.0

    # 예산 $3 → 83% → warn(임계 80)
    monkeypatch.setattr("app.services.ai_cost_service.get_settings",
                        lambda: _FakeSettings(3.0))
    out = await AiCostService(db_session).summary(days=30)
    assert out["budget"]["status"] == "warn"

    # 예산 $2 → 125% → over
    monkeypatch.setattr("app.services.ai_cost_service.get_settings",
                        lambda: _FakeSettings(2.0))
    out = await AiCostService(db_session).summary(days=30)
    assert out["budget"]["status"] == "over"


async def test_summary_respects_window(db_session: AsyncSession) -> None:
    run = await _make_run(db_session)
    old = AiModelResponse(
        run_id=run.id, provider="openai", model="gpt-5.4", role="primary_analysis",
        prompt_tokens=1000, completion_tokens=1000, total_tokens=2000,
    )
    db_session.add(old)
    await db_session.flush()
    # created_at을 40일 전으로 강제(서버 디폴트 후 업데이트)
    old.created_at = datetime.now(timezone.utc) - timedelta(days=40)
    await db_session.flush()

    out = await AiCostService(db_session).summary(days=30)
    assert out["total"]["responses"] == 0
