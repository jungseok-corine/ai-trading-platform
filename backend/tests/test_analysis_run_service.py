"""AI Analysis Run Service (Phase C-2.4 / C-2.4.1 / C-2.5) 통합 테스트.

검증 항목:
  1. fake provider로 analysis run 생성 성공
  2. run.status == succeeded 저장 확인
  3. ai_model_responses 저장 확인
  4. run 조회 API (GET /api/v1/analysis-runs/{run_id})
  5. strategy_version별 run 목록 API (GET /api/v1/strategies/.../analysis-runs)
  6. strategy/version not found → 서비스 None 반환
  7. 잘못된 strategy/version → API 404
  8. provider 실패 시 failed 상태 저장
  9. 미구현 provider → 400
  10. 알 수 없는 provider → 400
  11. unsupported prompt_type → 400
  12. run 목록 — 여러 run, 최신 순 확인
  13. 분석 run POST API 성공 (201)
  14. 응답 구조 — prompt_length / truncated / warnings 포함
  15. responses 포함 확인 (GET single run)
  --- C-2.4.1: Reproducibility ---
  16. input_payload 저장 확인
  17. input_hash 생성 확인
  18. prompt_hash 생성 확인
  19. 동일 입력 → 동일 input_hash
  20. 다른 prompt_type → 다른 input_hash
  21. GET run API 응답에 input_hash / prompt_hash 포함
  --- C-2.5: Dual-Model ---
  22. dual mode — responses 2개 저장
  23. dual mode — role이 primary_analysis / secondary_analysis
  24. dual mode — input_hash / prompt_hash 공유 (run 레벨)
  25. secondary_provider 누락 시 422 validation error
  26. dual mode secondary provider 실패 → run FAILED + 성공 response 보존
  27. unsupported secondary provider → 400
  28. API dual mode 성공 (201, 2 responses)
  29. mode 컬럼이 응답에 포함됨
"""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import AnalysisRunStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.main import app
from app.services.ai_analysis import AnalysisProviderError
from app.services.ai_analysis.run_service import AnalysisRunService

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _make_strategy_version(
    session: AsyncSession,
    symbol: str = "005930",
    name: str = "RunTestStrategy",
) -> tuple[Strategy, StrategyVersion]:
    strat = Strategy(name=name, description="analysis run test")
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
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _db_override(db_session: AsyncSession):
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    yield
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 1. fake provider로 analysis run 생성 성공
# ---------------------------------------------------------------------------


async def test_create_run_succeeds_with_fake_provider(db_session: AsyncSession) -> None:
    """fake provider로 run을 생성하면 None이 아닌 AiAnalysisRun이 반환된다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run = await svc.create_run(
        strategy_id=strat.id,
        version_id=ver.id,
        prompt_type="overview",
        provider_name="fake",
    )

    assert run is not None
    assert run.id is not None
    assert run.strategy_id == strat.id
    assert run.strategy_version_id == ver.id
    assert run.provider == "fake"
    assert run.model == "fake-1.0"
    assert run.prompt_type == "overview"


# ---------------------------------------------------------------------------
# 2. run.status == succeeded
# ---------------------------------------------------------------------------


async def test_create_run_status_succeeded(db_session: AsyncSession) -> None:
    """성공적으로 완료된 run의 status는 succeeded이다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run = await svc.create_run(strat.id, ver.id, "overview", "fake")

    assert run is not None
    assert run.status == AnalysisRunStatus.SUCCEEDED
    assert run.completed_at is not None
    assert run.started_at is not None
    assert run.error_message is None


# ---------------------------------------------------------------------------
# 3. ai_model_responses 저장 확인
# ---------------------------------------------------------------------------


async def test_create_run_saves_model_response(db_session: AsyncSession) -> None:
    """run 생성 후 responses에 primary_analysis 응답이 1개 저장된다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run = await svc.create_run(strat.id, ver.id, "overview", "fake")

    assert run is not None
    assert len(run.responses) == 1
    resp = run.responses[0]
    assert resp.provider == "fake"
    assert resp.model == "fake-1.0"
    assert resp.role == "primary_analysis"
    assert isinstance(resp.content, str)
    assert len(resp.content) > 0
    assert resp.prompt_tokens is not None
    assert resp.total_tokens is not None
    assert resp.latency_ms is not None
    assert resp.finish_reason == "stop"
    assert resp.error_message is None


# ---------------------------------------------------------------------------
# 4. GET /api/v1/analysis-runs/{run_id}
# ---------------------------------------------------------------------------


async def test_api_get_run_by_id(db_session: AsyncSession) -> None:
    """GET /analysis-runs/{run_id}가 run과 responses를 반환한다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)
    run = await svc.create_run(strat.id, ver.id, "overview", "fake")
    assert run is not None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/analysis-runs/{run.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == run.id
    assert body["status"] == "succeeded"
    assert body["provider"] == "fake"
    assert isinstance(body["responses"], list)
    assert len(body["responses"]) == 1
    assert body["responses"][0]["role"] == "primary_analysis"


async def test_api_get_run_not_found(db_session: AsyncSession) -> None:
    """존재하지 않는 run_id → 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/analysis-runs/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. GET .../analysis-runs (list)
# ---------------------------------------------------------------------------


async def test_api_list_runs_for_version(db_session: AsyncSession) -> None:
    """GET .../versions/{version_id}/analysis-runs가 해당 버전의 run 목록을 반환한다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)
    await svc.create_run(strat.id, ver.id, "overview", "fake")
    await svc.create_run(strat.id, ver.id, "risk", "fake")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs"
        )

    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 2


# ---------------------------------------------------------------------------
# 6. strategy/version not found → 서비스 None 반환
# ---------------------------------------------------------------------------


async def test_create_run_returns_none_for_missing_version(db_session: AsyncSession) -> None:
    """존재하지 않는 strategy_id/version_id → service.create_run() returns None."""
    svc = AnalysisRunService(db_session)
    run = await svc.create_run(9999, 9999, "overview", "fake")
    assert run is None


# ---------------------------------------------------------------------------
# 7. 잘못된 strategy/version → API 404
# ---------------------------------------------------------------------------


async def test_api_create_run_404_for_missing_version(db_session: AsyncSession) -> None:
    """존재하지 않는 strategy/version → POST 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/strategies/9999/versions/9999/analysis-runs",
            json={"prompt_type": "overview", "provider": "fake"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. provider 실패 시 failed 상태 저장
# ---------------------------------------------------------------------------


async def test_create_run_status_failed_on_provider_error(db_session: AsyncSession) -> None:
    """provider.analyze()가 AnalysisProviderError를 발생시키면 run.status == failed."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    with patch(
        "app.services.ai_analysis.fake.FakeAnalysisProvider.analyze",
        new_callable=AsyncMock,
        side_effect=AnalysisProviderError(
            provider="fake",
            message="simulated provider failure",
            retryable=False,
        ),
    ):
        run = await svc.create_run(strat.id, ver.id, "overview", "fake")

    assert run is not None
    assert run.status == AnalysisRunStatus.FAILED
    assert run.error_message == "simulated provider failure"
    assert run.completed_at is not None


async def test_create_run_failed_response_saved(db_session: AsyncSession) -> None:
    """provider 실패 시 responses에 error_message가 있는 응답이 저장된다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    with patch(
        "app.services.ai_analysis.fake.FakeAnalysisProvider.analyze",
        new_callable=AsyncMock,
        side_effect=AnalysisProviderError(
            provider="fake",
            message="simulated failure",
            retryable=True,
        ),
    ):
        run = await svc.create_run(strat.id, ver.id, "overview", "fake")

    assert run is not None
    assert len(run.responses) == 1
    assert run.responses[0].finish_reason == "error"
    assert run.responses[0].error_message == "simulated failure"
    assert run.responses[0].content is None


# ---------------------------------------------------------------------------
# 9. 미구현 provider → 400
# ---------------------------------------------------------------------------


async def test_api_create_run_400_for_unimplemented_provider(db_session: AsyncSession) -> None:
    """알 수 없는 provider → 400 (unknown-llm은 _SUPPORTED_PROVIDERS에 없음)."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={"prompt_type": "overview", "provider": "unknown-llm"},
        )

    assert resp.status_code == 400
    assert "unknown-llm" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 10. 알 수 없는 provider → 400
# ---------------------------------------------------------------------------


async def test_api_create_run_400_for_unknown_provider(db_session: AsyncSession) -> None:
    """알 수 없는 provider 이름 → 400."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={"prompt_type": "overview", "provider": "banana-llm"},
        )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 11. unsupported prompt_type → 400
# ---------------------------------------------------------------------------


async def test_api_create_run_400_for_bad_prompt_type(db_session: AsyncSession) -> None:
    """지원하지 않는 prompt_type → 400."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={"prompt_type": "not_a_valid_type", "provider": "fake"},
        )

    assert resp.status_code == 400
    assert "not_a_valid_type" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 12. 여러 run 목록 — 최신 순
# ---------------------------------------------------------------------------


async def test_list_runs_ordered_by_latest(db_session: AsyncSession) -> None:
    """list_runs_for_version은 created_at 내림차순으로 반환한다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run1 = await svc.create_run(strat.id, ver.id, "overview", "fake")
    run2 = await svc.create_run(strat.id, ver.id, "risk", "fake")
    run3 = await svc.create_run(strat.id, ver.id, "improvement", "fake")

    runs = await svc.list_runs_for_version(strat.id, ver.id)

    assert len(runs) == 3
    assert runs[0].id == run3.id   # 가장 최신
    assert runs[2].id == run1.id   # 가장 오래됨


# ---------------------------------------------------------------------------
# 13. POST API 성공 (201)
# ---------------------------------------------------------------------------


async def test_api_create_run_returns_201(db_session: AsyncSession) -> None:
    """POST /analysis-runs는 201과 AnalysisRunRead를 반환한다."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={"prompt_type": "overview", "provider": "fake"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["strategy_id"] == strat.id
    assert body["strategy_version_id"] == ver.id
    assert body["status"] == "succeeded"
    assert body["provider"] == "fake"
    assert body["prompt_type"] == "overview"


# ---------------------------------------------------------------------------
# 14. 응답 구조 — prompt_length / truncated / warnings / analysis_type
# ---------------------------------------------------------------------------


async def test_api_create_run_response_structure(db_session: AsyncSession) -> None:
    """POST 응답에 prompt_length, truncated, warnings, analysis_type이 포함된다."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={"prompt_type": "overview", "provider": "fake"},
        )

    body = resp.json()
    assert body["analysis_type"] == "strategy_performance"
    assert body["target_type"] == "strategy_version"
    assert isinstance(body["prompt_length"], int)
    assert body["prompt_length"] > 0
    assert isinstance(body["truncated"], bool)
    assert body["warnings"] is None or isinstance(body["warnings"], list)


# ---------------------------------------------------------------------------
# 15. GET single run — responses 포함
# ---------------------------------------------------------------------------


async def test_get_run_includes_responses(db_session: AsyncSession) -> None:
    """get_run()이 responses 관계를 포함해 반환한다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)
    created = await svc.create_run(strat.id, ver.id, "risk", "fake")
    assert created is not None

    fetched = await svc.get_run(created.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert len(fetched.responses) == 1
    assert fetched.responses[0].provider == "fake"
    assert fetched.responses[0].total_tokens is not None


# ---------------------------------------------------------------------------
# 16. input_payload 저장 확인  (C-2.4.1)
# ---------------------------------------------------------------------------


async def test_create_run_saves_input_payload(db_session: AsyncSession) -> None:
    """run 생성 시 input_payload가 JSONB로 저장된다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run = await svc.create_run(strat.id, ver.id, "overview", "fake")

    assert run is not None
    assert run.input_payload is not None
    assert isinstance(run.input_payload, dict)
    # StrategyAnalysisInputRead 필드 확인
    assert "strategy" in run.input_payload
    assert run.input_payload["strategy"]["strategy_id"] == strat.id
    assert run.input_payload["strategy"]["strategy_version_id"] == ver.id


# ---------------------------------------------------------------------------
# 17. input_hash 생성 확인  (C-2.4.1)
# ---------------------------------------------------------------------------


async def test_create_run_generates_input_hash(db_session: AsyncSession) -> None:
    """run 생성 시 input_hash가 64자 SHA256 hex string으로 저장된다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run = await svc.create_run(strat.id, ver.id, "overview", "fake")

    assert run is not None
    assert run.input_hash is not None
    assert isinstance(run.input_hash, str)
    assert len(run.input_hash) == 64
    # hex string
    int(run.input_hash, 16)  # raises ValueError if not valid hex


# ---------------------------------------------------------------------------
# 18. prompt_hash 생성 확인  (C-2.4.1)
# ---------------------------------------------------------------------------


async def test_create_run_generates_prompt_hash(db_session: AsyncSession) -> None:
    """run 생성 시 prompt_hash가 64자 SHA256 hex string으로 저장된다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run = await svc.create_run(strat.id, ver.id, "overview", "fake")

    assert run is not None
    assert run.prompt_hash is not None
    assert isinstance(run.prompt_hash, str)
    assert len(run.prompt_hash) == 64
    int(run.prompt_hash, 16)  # valid hex


# ---------------------------------------------------------------------------
# 19. 동일 입력 → 동일 input_hash  (C-2.4.1)
# ---------------------------------------------------------------------------


async def test_same_input_produces_same_input_hash(db_session: AsyncSession) -> None:
    """동일한 strategy_version + prompt_type + provider + model → input_hash 동일."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run1 = await svc.create_run(strat.id, ver.id, "overview", "fake")
    run2 = await svc.create_run(strat.id, ver.id, "overview", "fake")

    assert run1 is not None and run2 is not None
    assert run1.input_hash == run2.input_hash


# ---------------------------------------------------------------------------
# 20. 다른 prompt_type → 다른 input_hash  (C-2.4.1)
# ---------------------------------------------------------------------------


async def test_different_prompt_type_produces_different_input_hash(db_session: AsyncSession) -> None:
    """prompt_type이 달라지면 input_hash도 달라진다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run_overview = await svc.create_run(strat.id, ver.id, "overview", "fake")
    run_risk = await svc.create_run(strat.id, ver.id, "risk", "fake")

    assert run_overview is not None and run_risk is not None
    assert run_overview.input_hash != run_risk.input_hash


# ---------------------------------------------------------------------------
# 21. GET run API 응답에 input_hash / prompt_hash 포함  (C-2.4.1)
# ---------------------------------------------------------------------------


async def test_api_get_run_includes_hashes(db_session: AsyncSession) -> None:
    """GET /analysis-runs/{run_id} 응답 JSON에 input_hash와 prompt_hash가 포함된다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)
    run = await svc.create_run(strat.id, ver.id, "overview", "fake")
    assert run is not None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/analysis-runs/{run.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert "input_hash" in body
    assert "prompt_hash" in body
    assert body["input_hash"] is not None
    assert len(body["input_hash"]) == 64
    assert body["prompt_hash"] is not None
    assert len(body["prompt_hash"]) == 64


# ---------------------------------------------------------------------------
# 22. dual mode — responses 2개 저장  (C-2.5)
# ---------------------------------------------------------------------------


async def test_dual_mode_saves_two_responses(db_session: AsyncSession) -> None:
    """dual mode로 생성된 run은 ai_model_responses가 2개이다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run = await svc.create_run(
        strat.id, ver.id, "overview", "fake",
        mode="dual",
        secondary_provider_name="fake",
        secondary_model="fake-claude-1.0",
    )

    assert run is not None
    assert len(run.responses) == 2


# ---------------------------------------------------------------------------
# 23. dual mode — role  (C-2.5)
# ---------------------------------------------------------------------------


async def test_dual_mode_response_roles(db_session: AsyncSession) -> None:
    """dual mode responses의 role이 primary_analysis / secondary_analysis이다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run = await svc.create_run(
        strat.id, ver.id, "overview", "fake",
        mode="dual",
        secondary_provider_name="fake",
        secondary_model="fake-claude-1.0",
    )

    assert run is not None
    roles = {r.role for r in run.responses}
    assert roles == {"primary_analysis", "secondary_analysis"}


# ---------------------------------------------------------------------------
# 24. dual mode — input_hash / prompt_hash 공유  (C-2.5)
# ---------------------------------------------------------------------------


async def test_dual_mode_shares_hashes(db_session: AsyncSession) -> None:
    """dual mode run은 input_hash / prompt_hash가 run 레벨에서 공유된다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run = await svc.create_run(
        strat.id, ver.id, "overview", "fake",
        mode="dual",
        secondary_provider_name="fake",
        secondary_model="fake-claude-1.0",
    )

    assert run is not None
    assert run.input_hash is not None
    assert len(run.input_hash) == 64
    assert run.prompt_hash is not None
    assert len(run.prompt_hash) == 64
    # 두 responses 모두 같은 run에 속하므로 hash는 run 레벨에서 공유됨
    assert len(run.responses) == 2
    assert all(r.run_id == run.id for r in run.responses)


# ---------------------------------------------------------------------------
# 25. secondary_provider 누락 → 422 validation error  (C-2.5)
# ---------------------------------------------------------------------------


async def test_api_dual_mode_missing_secondary_provider_returns_422(
    db_session: AsyncSession,
) -> None:
    """dual mode에서 secondary_provider 없이 요청하면 422 (Pydantic validation error)."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={"prompt_type": "overview", "mode": "dual", "provider": "fake"},
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 26. dual mode secondary 실패 → run FAILED + 성공 response 보존  (C-2.5)
# ---------------------------------------------------------------------------


async def test_dual_mode_secondary_failure_preserves_primary_response(
    db_session: AsyncSession,
) -> None:
    """dual mode에서 secondary 실패 시 run.status=FAILED, primary response는 보존된다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    from app.services.ai_analysis.schemas import AnalysisProviderResult

    _primary_result = AnalysisProviderResult(
        provider="fake", model="fake-1.0", content="primary ok",
        prompt_tokens=10, completion_tokens=5, total_tokens=15,
        latency_ms=42, finish_reason="stop", raw=None,
    )
    call_count = 0

    async def _flaky_analyze(prompt: str, *, model=None, timeout_seconds=None):
        nonlocal call_count
        call_count += 1
        if call_count == 2:  # secondary call
            raise AnalysisProviderError(provider="fake", message="secondary failure")
        return _primary_result

    with patch(
        "app.services.ai_analysis.fake.FakeAnalysisProvider.analyze",
        new_callable=AsyncMock,
        side_effect=_flaky_analyze,
    ):
        run = await svc.create_run(
            strat.id, ver.id, "overview", "fake",
            mode="dual",
            secondary_provider_name="fake",
            secondary_model="fake-claude-1.0",
        )

    assert run is not None
    assert run.status == AnalysisRunStatus.FAILED
    assert run.error_message is not None
    assert "secondary" in run.error_message.lower()
    # 두 responses 모두 저장되어야 함 (primary 성공 + secondary 에러)
    assert len(run.responses) == 2
    primary_resp = next(r for r in run.responses if r.role == "primary_analysis")
    secondary_resp = next(r for r in run.responses if r.role == "secondary_analysis")
    assert primary_resp.content is not None
    assert primary_resp.finish_reason == "stop"
    assert secondary_resp.finish_reason == "error"
    assert secondary_resp.error_message == "secondary failure"


# ---------------------------------------------------------------------------
# 27. unsupported secondary provider → 400  (C-2.5)
# ---------------------------------------------------------------------------


async def test_api_dual_mode_unsupported_secondary_provider_returns_400(
    db_session: AsyncSession,
) -> None:
    """dual mode에서 알 수 없는 secondary provider (unknown-llm) → 400."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={
                "prompt_type": "overview",
                "mode": "dual",
                "provider": "fake",
                "secondary_provider": "unknown-llm",
            },
        )

    assert resp.status_code == 400
    assert "unknown-llm" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 28. API dual mode 성공 (201, 2 responses)  (C-2.5)
# ---------------------------------------------------------------------------


async def test_api_dual_mode_returns_201_with_two_responses(db_session: AsyncSession) -> None:
    """POST dual mode → 201, responses에 2개의 항목이 있다."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={
                "prompt_type": "overview",
                "mode": "dual",
                "provider": "fake",
                "secondary_provider": "fake",
                "secondary_model": "fake-claude-1.0",
            },
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["mode"] == "dual"
    assert body["status"] == "succeeded"
    assert len(body["responses"]) == 2
    roles = {r["role"] for r in body["responses"]}
    assert roles == {"primary_analysis", "secondary_analysis"}


# ---------------------------------------------------------------------------
# 29. mode 컬럼이 API 응답에 포함됨  (C-2.5)
# ---------------------------------------------------------------------------


async def test_api_single_mode_response_includes_mode_field(db_session: AsyncSession) -> None:
    """단일 모드 POST 응답에도 mode='single' 필드가 포함된다."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={"prompt_type": "overview", "provider": "fake"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert "mode" in body
    assert body["mode"] == "single"


# ===========================================================================
# C-2.6: Critique + Synthesis Workflow
# ===========================================================================

_DUAL_BASE = {
    "prompt_type": "overview",
    "mode": "dual",
    "provider": "fake",
    "secondary_provider": "fake",
    "secondary_model": "fake-claude-1.0",
}


# ---------------------------------------------------------------------------
# 30. dual + critique 성공 — responses 4개  (C-2.6)
# ---------------------------------------------------------------------------


async def test_dual_critique_saves_four_responses(db_session: AsyncSession) -> None:
    """dual + enable_critique → responses 4개 (primary/secondary analysis + 2 critiques)."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run = await svc.create_run(
        strat.id, ver.id, "overview", "fake",
        mode="dual",
        secondary_provider_name="fake",
        secondary_model="fake-claude-1.0",
        enable_critique=True,
    )

    assert run is not None
    assert run.status == AnalysisRunStatus.SUCCEEDED
    assert len(run.responses) == 4


# ---------------------------------------------------------------------------
# 31. dual + synthesis only — responses 3개  (C-2.6)
# ---------------------------------------------------------------------------


async def test_dual_synthesis_only_saves_three_responses(db_session: AsyncSession) -> None:
    """dual + enable_synthesis (critique 없음) → responses 3개."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run = await svc.create_run(
        strat.id, ver.id, "overview", "fake",
        mode="dual",
        secondary_provider_name="fake",
        secondary_model="fake-claude-1.0",
        enable_synthesis=True,
    )

    assert run is not None
    assert run.status == AnalysisRunStatus.SUCCEEDED
    assert len(run.responses) == 3
    roles = {r.role for r in run.responses}
    assert roles == {"primary_analysis", "secondary_analysis", "synthesis"}


# ---------------------------------------------------------------------------
# 32. dual + critique + synthesis — responses 5개  (C-2.6)
# ---------------------------------------------------------------------------


async def test_dual_critique_synthesis_saves_five_responses(db_session: AsyncSession) -> None:
    """dual + enable_critique + enable_synthesis → responses 5개."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

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
    assert len(run.responses) == 5


# ---------------------------------------------------------------------------
# 33. role 종류 테스트  (C-2.6)
# ---------------------------------------------------------------------------


async def test_debate_response_roles(db_session: AsyncSession) -> None:
    """dual + critique + synthesis의 모든 role이 올바르게 저장된다."""
    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    run = await svc.create_run(
        strat.id, ver.id, "overview", "fake",
        mode="dual",
        secondary_provider_name="fake",
        secondary_model="fake-claude-1.0",
        enable_critique=True,
        enable_synthesis=True,
    )

    assert run is not None
    roles = {r.role for r in run.responses}
    assert roles == {
        "primary_analysis",
        "secondary_analysis",
        "primary_critique",
        "secondary_critique",
        "synthesis",
    }


# ---------------------------------------------------------------------------
# 34. single mode + enable_critique → 422  (C-2.6)
# ---------------------------------------------------------------------------


async def test_api_single_mode_with_critique_returns_422(db_session: AsyncSession) -> None:
    """mode='single'에서 enable_critique=True → 422 validation error."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={
                "prompt_type": "overview",
                "mode": "single",
                "provider": "fake",
                "enable_critique": True,
            },
        )

    assert resp.status_code == 422


async def test_api_single_mode_with_synthesis_returns_422(db_session: AsyncSession) -> None:
    """mode='single'에서 enable_synthesis=True → 422 validation error."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={
                "prompt_type": "overview",
                "mode": "single",
                "provider": "fake",
                "enable_synthesis": True,
            },
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 35. critique 실패 → run FAILED + 기존 analysis 응답 보존  (C-2.6)
# ---------------------------------------------------------------------------


async def test_critique_failure_preserves_analysis_responses(db_session: AsyncSession) -> None:
    """primary_critique 실패 시 analysis 2개 + critique 2개(성공+에러)가 저장되고 run=FAILED."""
    from app.services.ai_analysis.schemas import AnalysisProviderResult

    _ok = AnalysisProviderResult(
        provider="fake", model="fake-1.0", content="ok",
        prompt_tokens=5, completion_tokens=5, total_tokens=10,
        latency_ms=42, finish_reason="stop", raw=None,
    )
    call_count = 0

    async def _side(prompt: str, *, model=None, timeout_seconds=None):
        nonlocal call_count
        call_count += 1
        if call_count == 3:   # primary_critique (3rd call)
            raise AnalysisProviderError(provider="fake", message="primary critique failed")
        return _ok

    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    with patch(
        "app.services.ai_analysis.fake.FakeAnalysisProvider.analyze",
        new_callable=AsyncMock,
        side_effect=_side,
    ):
        run = await svc.create_run(
            strat.id, ver.id, "overview", "fake",
            mode="dual",
            secondary_provider_name="fake",
            secondary_model="fake-claude-1.0",
            enable_critique=True,
        )

    assert run is not None
    assert run.status == AnalysisRunStatus.FAILED
    assert run.error_message is not None
    assert "primary_critique" in run.error_message
    # call order: primary(1), secondary(2), primary_critique(3-fail), secondary_critique(4-ok)
    assert len(run.responses) == 4
    roles = {r.role for r in run.responses}
    assert "primary_analysis" in roles
    assert "secondary_analysis" in roles
    assert "primary_critique" in roles
    assert "secondary_critique" in roles
    p_crit = next(r for r in run.responses if r.role == "primary_critique")
    assert p_crit.finish_reason == "error"
    s_crit = next(r for r in run.responses if r.role == "secondary_critique")
    assert s_crit.content == "ok"


# ---------------------------------------------------------------------------
# 36. synthesis 실패 → run FAILED + analysis/critique 보존  (C-2.6)
# ---------------------------------------------------------------------------


async def test_synthesis_failure_preserves_analysis_and_critique(db_session: AsyncSession) -> None:
    """synthesis 실패 시 analysis 2개 + critique 2개 + synthesis(에러) = 5개 저장, run=FAILED."""
    from app.services.ai_analysis.schemas import AnalysisProviderResult

    _ok = AnalysisProviderResult(
        provider="fake", model="fake-1.0", content="ok",
        prompt_tokens=5, completion_tokens=5, total_tokens=10,
        latency_ms=42, finish_reason="stop", raw=None,
    )
    call_count = 0

    async def _side(prompt: str, *, model=None, timeout_seconds=None):
        nonlocal call_count
        call_count += 1
        if call_count == 5:   # synthesis (5th call)
            raise AnalysisProviderError(provider="fake", message="synthesis failed")
        return _ok

    strat, ver = await _make_strategy_version(db_session)
    svc = AnalysisRunService(db_session)

    with patch(
        "app.services.ai_analysis.fake.FakeAnalysisProvider.analyze",
        new_callable=AsyncMock,
        side_effect=_side,
    ):
        run = await svc.create_run(
            strat.id, ver.id, "overview", "fake",
            mode="dual",
            secondary_provider_name="fake",
            secondary_model="fake-claude-1.0",
            enable_critique=True,
            enable_synthesis=True,
        )

    assert run is not None
    assert run.status == AnalysisRunStatus.FAILED
    assert "synthesis" in (run.error_message or "")
    assert len(run.responses) == 5
    synth = next(r for r in run.responses if r.role == "synthesis")
    assert synth.finish_reason == "error"
    assert synth.error_message == "synthesis failed"
    # analysis/critique 응답은 성공적으로 보존
    success_roles = {r.role for r in run.responses if r.finish_reason != "error"}
    assert success_roles == {
        "primary_analysis", "secondary_analysis", "primary_critique", "secondary_critique"
    }


# ---------------------------------------------------------------------------
# 37. API debate 전체 성공 테스트  (C-2.6)
# ---------------------------------------------------------------------------


async def test_api_debate_full_returns_201_five_responses(db_session: AsyncSession) -> None:
    """API POST with critique+synthesis → 201, responses 5개."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={
                **_DUAL_BASE,
                "enable_critique": True,
                "enable_synthesis": True,
            },
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "succeeded"
    assert len(body["responses"]) == 5
    roles = {r["role"] for r in body["responses"]}
    assert roles == {
        "primary_analysis",
        "secondary_analysis",
        "primary_critique",
        "secondary_critique",
        "synthesis",
    }
