"""AI Analysis Run Service (Phase C-2.4 / C-2.4.1) 통합 테스트.

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
    """openai/anthropic provider는 아직 미구현 → 400."""
    strat, ver = await _make_strategy_version(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-runs",
            json={"prompt_type": "overview", "provider": "openai"},
        )

    assert resp.status_code == 400
    assert "openai" in resp.json()["detail"].lower()


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
