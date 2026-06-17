"""AI analysis run DB 영속성 테스트 (C-2.7.6.1).

핵심 검증:
  service.commit()이 실제로 데이터를 DB에 저장하는지 확인한다.
  같은 session identity map으로 조회하지 않고 반드시 새 session에서 조회한다.
  (flush만 된 상태 vs commit된 상태를 구분하기 위함)

픽스처 설명:
  db_session_with_factory: (session, factory) 튜플 반환.
    - session: 테스트에서 API/service에 주입하는 primary session.
    - factory: 추가 session을 만들 때 사용. 같은 connection 위에 있으므로
               service.commit() (=savepoint release) 이후 데이터를 볼 수 있다.
    - 테스트 종료 시 outer transaction 롤백 → 다른 테스트에 영향 없음.
"""
from __future__ import annotations

from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.domain.models.ai_analysis import AiAnalysisRun, AiModelResponse
from app.domain.models.enums import AnalysisRunStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.main import app
from app.services.ai_analysis import AnalysisProviderError
from app.services.ai_analysis.run_service import AnalysisRunService
from scripts.ai_dual_debate_smoke_test import run_debate

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _make_strategy_version(
    session: AsyncSession,
    symbol: str = "005930",
    name: str = "PersistTestStrategy",
) -> tuple[Strategy, StrategyVersion]:
    strat = Strategy(name=name, description="persistence test")
    session.add(strat)
    await session.flush()
    ver = StrategyVersion(
        strategy_id=strat.id,
        version_no=1,
        parameters={
            "strategy_type": "moving_average_cross",
            "symbol_code": symbol,
            "short_window": 5,
            "long_window": 20,
            "timeframe": "1m",
        },
    )
    session.add(ver)
    await session.flush()
    return strat, ver


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


# ---------------------------------------------------------------------------
# 1. API 호출 후 새 session에서 ai_analysis_runs row가 조회된다
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_run_persists_ai_analysis_runs_row(db_session_with_factory) -> None:
    """POST analysis-runs 후 새 session에서 ai_analysis_runs row가 조회된다."""
    session, factory = db_session_with_factory
    strat, ver = await _make_strategy_version(session)

    app.dependency_overrides[get_db] = _override_get_db(session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
                json={"prompt_type": "overview", "provider": "fake"},
            )
        assert resp.status_code == 201
        run_id = resp.json()["id"]
    finally:
        app.dependency_overrides.pop(get_db, None)

    async with factory() as session2:
        row = await session2.get(AiAnalysisRun, run_id)
        assert row is not None, "run row가 새 session에서 조회되지 않음 — commit이 누락됨"
        assert row.id == run_id
        assert row.strategy_id == strat.id


# ---------------------------------------------------------------------------
# 2. API 호출 후 새 session에서 ai_model_responses row가 조회된다
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_run_persists_ai_model_responses_row(db_session_with_factory) -> None:
    """POST analysis-runs 후 새 session에서 ai_model_responses row가 조회된다."""
    session, factory = db_session_with_factory
    strat, ver = await _make_strategy_version(session)

    app.dependency_overrides[get_db] = _override_get_db(session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
                json={"prompt_type": "overview", "provider": "fake"},
            )
        assert resp.status_code == 201
        run_id = resp.json()["id"]
    finally:
        app.dependency_overrides.pop(get_db, None)

    async with factory() as session2:
        result = await session2.execute(
            select(AiModelResponse).where(AiModelResponse.run_id == run_id)
        )
        responses = result.scalars().all()
        assert len(responses) == 1, "responses row가 새 session에서 조회되지 않음 — commit이 누락됨"
        assert responses[0].role == "primary_analysis"
        assert responses[0].provider == "fake"


# ---------------------------------------------------------------------------
# 3. 새 session에서 run.status=succeeded가 유지된다
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_run_status_succeeded_visible_in_new_session(db_session_with_factory) -> None:
    """성공 run의 status=succeeded가 새 session에서도 조회된다."""
    session, factory = db_session_with_factory
    strat, ver = await _make_strategy_version(session)

    app.dependency_overrides[get_db] = _override_get_db(session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
                json={"prompt_type": "overview", "provider": "fake"},
            )
        assert resp.status_code == 201
        run_id = resp.json()["id"]
    finally:
        app.dependency_overrides.pop(get_db, None)

    async with factory() as session2:
        row = await session2.get(AiAnalysisRun, run_id)
        assert row is not None
        assert row.status == AnalysisRunStatus.SUCCEEDED
        assert row.completed_at is not None
        assert row.error_message is None


# ---------------------------------------------------------------------------
# 4. provider 실패 시 run.status=failed와 error response가 새 session에서 유지된다
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_run_persists_in_new_session(db_session_with_factory) -> None:
    """provider 실패 run의 status=failed와 error response가 새 session에서 조회된다."""
    session, factory = db_session_with_factory
    strat, ver = await _make_strategy_version(session)
    svc = AnalysisRunService(session)

    with patch(
        "app.services.ai_analysis.fake.FakeAnalysisProvider.analyze",
        new_callable=AsyncMock,
        side_effect=AnalysisProviderError(
            provider="fake",
            message="simulated failure for persistence test",
            retryable=False,
        ),
    ):
        run = await svc.create_run(strat.id, ver.id, "overview", "fake")

    assert run is not None
    run_id = run.id

    async with factory() as session2:
        row = await session2.get(AiAnalysisRun, run_id)
        assert row is not None
        assert row.status == AnalysisRunStatus.FAILED
        assert row.error_message == "simulated failure for persistence test"
        assert row.completed_at is not None

        result = await session2.execute(
            select(AiModelResponse).where(AiModelResponse.run_id == run_id)
        )
        responses = result.scalars().all()
        assert len(responses) == 1
        assert responses[0].finish_reason == "error"
        assert responses[0].error_message == "simulated failure for persistence test"


# ---------------------------------------------------------------------------
# 5. dual + critique + synthesis full debate — 새 session에서 responses 5개 조회
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_debate_run_five_responses_in_new_session(db_session_with_factory) -> None:
    """dual + critique + synthesis run이 새 session에서 responses 5개로 조회된다."""
    session, factory = db_session_with_factory
    strat, ver = await _make_strategy_version(session)
    svc = AnalysisRunService(session)

    run = await svc.create_run(
        strat.id, ver.id, "overview", "fake",
        mode="dual",
        secondary_provider_name="fake",
        secondary_model="fake-claude-1.0",
        enable_critique=True,
        enable_synthesis=True,
    )

    assert run is not None
    assert run.status == AnalysisRunStatus.SUCCEEDED
    run_id = run.id

    async with factory() as session2:
        result = await session2.execute(
            select(AiAnalysisRun)
            .where(AiAnalysisRun.id == run_id)
            .options(selectinload(AiAnalysisRun.responses))
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.status == AnalysisRunStatus.SUCCEEDED
        assert len(row.responses) == 5, f"responses {len(row.responses)}개 — commit이 누락됐거나 불완전함"

        roles = {r.role for r in row.responses}
        assert roles == {
            "primary_analysis",
            "secondary_analysis",
            "primary_critique",
            "secondary_critique",
            "synthesis",
        }


# ---------------------------------------------------------------------------
# 6. script 경로: run_debate()가 service를 통해 DB에 저장한다
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_script_run_debate_persists_via_service(db_session_with_factory) -> None:
    """smoke script의 run_debate()가 실제 service를 통해 DB에 저장된다.

    scripts/ai_dual_debate_smoke_test.py의 run_debate() 함수에
    실제 AnalysisRunService(session)를 주입해 실행한다.
    """
    session, factory = db_session_with_factory
    strat, ver = await _make_strategy_version(session)
    svc = AnalysisRunService(session)

    out = StringIO()
    exit_code = await run_debate(
        svc,
        strategy_id=strat.id,
        version_id=ver.id,
        prompt_type="overview",
        provider="fake",
        secondary_provider="fake",
        file=out,
    )

    assert exit_code == 0

    output = out.getvalue()
    assert "SUCCEEDED" in output

    async with factory() as session2:
        result = await session2.execute(
            select(AiAnalysisRun).where(AiAnalysisRun.strategy_id == strat.id)
        )
        rows = result.scalars().all()
        assert len(rows) >= 1, "script run_debate()가 DB에 저장하지 않음 — commit 누락 또는 session 문제"
        assert rows[0].status == AnalysisRunStatus.SUCCEEDED


# ---------------------------------------------------------------------------
# 7. finish_reason=length 경고 출력 확인
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_print_run_result_warns_on_length_finish_reason() -> None:
    """finish_reason=length인 response가 있으면 WARNING이 출력된다."""
    from types import SimpleNamespace

    from scripts.ai_dual_debate_smoke_test import print_run_result

    responses = [
        SimpleNamespace(
            role="primary_analysis", provider="openai", model="gpt-4o",
            error_message=None, prompt_tokens=100, completion_tokens=400,
            total_tokens=500, latency_ms=1000, finish_reason="stop",
            content="OpenAI analysis complete.",
        ),
        SimpleNamespace(
            role="secondary_analysis", provider="anthropic", model="claude-sonnet-4-6",
            error_message=None, prompt_tokens=150, completion_tokens=2048,
            total_tokens=2198, latency_ms=40000, finish_reason="length",
            content="Anthropic analysis truncated mid-sentence...",
        ),
    ]
    run = SimpleNamespace(
        id=42, status=SimpleNamespace(value="succeeded"),
        input_hash="abc123", prompt_hash="def456",
        error_message=None, responses=responses,
    )

    out = StringIO()
    print_run_result(run, file=out)
    output = out.getvalue()

    assert "WARNING" in output
    assert "secondary_analysis" in output
    assert "finish_reason=length" in output
    assert "AI_ANTHROPIC_MAX_TOKENS" in output


# ---------------------------------------------------------------------------
# 8. finish_reason=stop만 있으면 WARNING 없음
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_print_run_result_no_warning_when_all_stop() -> None:
    """모든 response가 finish_reason=stop이면 WARNING이 출력되지 않는다."""
    from types import SimpleNamespace

    from scripts.ai_dual_debate_smoke_test import print_run_result

    responses = [
        SimpleNamespace(
            role="primary_analysis", provider="openai", model="gpt-4o",
            error_message=None, prompt_tokens=100, completion_tokens=400,
            total_tokens=500, latency_ms=1000, finish_reason="stop",
            content="Complete.",
        ),
    ]
    run = SimpleNamespace(
        id=1, status=SimpleNamespace(value="succeeded"),
        input_hash="abc", prompt_hash="def",
        error_message=None, responses=responses,
    )

    out = StringIO()
    print_run_result(run, file=out)
    output = out.getvalue()

    assert "WARNING" not in output
