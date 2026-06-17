"""AI Provider Readiness API 테스트 (C-2.7.3).

실제 LLM 호출 없음 — 설정 상태만 확인한다.

검증 항목:
  1.  fake → status="available", configured=True
  2.  fake → missing_settings 빈 목록
  3.  openai api_key 없음 → status="missing_config", configured=False
  4.  openai api_key 있음 → status="available", configured=True
  5.  openai api_key 없음 → missing_settings=["AI_OPENAI_API_KEY"]
  6.  openai api_key 있음 → missing_settings 빈 목록
  7.  anthropic api_key 없음 → status="missing_config", configured=False
  8.  anthropic api_key 있음 → status="available", configured=True
  9.  anthropic api_key 없음 → missing_settings=["AI_ANTHROPIC_API_KEY"]
  10. anthropic api_key 있음 → missing_settings 빈 목록
  11. 알 수 없는 provider → get_provider_status() returns None
  12. list_provider_statuses() → 3개 항목 (fake, openai, anthropic 순)
  13. GET /api/v1/ai-analysis/providers → 200, 3개 항목
  14. GET /api/v1/ai-analysis/providers/fake → 200, available
  15. GET /api/v1/ai-analysis/providers/openai (no key) → 200, missing_config
  16. GET /api/v1/ai-analysis/providers/anthropic (no key) → 200, missing_config
  17. GET /api/v1/ai-analysis/providers/unknown-llm → 404
  18. fake → implemented=True
  19. openai → implemented=True
  20. anthropic → implemented=True
  21. default_model 필드 확인 (fake, openai, anthropic)
  22. note 필드 — api_key 있을 때 None, 없을 때 문자열
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.ai_analysis.readiness_schemas import AIProviderStatusRead
from app.services.ai_analysis.readiness_service import AIProviderReadinessService

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_SVC_MODULE = "app.services.ai_analysis.readiness_service.get_settings"


def _mock_settings(*, openai_key: str | None = None, anthropic_key: str | None = None) -> MagicMock:
    s = MagicMock()
    s.ai_openai_api_key = openai_key
    s.ai_openai_model = "gpt-4o"
    s.ai_openai_timeout_seconds = 60
    s.ai_anthropic_api_key = anthropic_key
    s.ai_anthropic_model = "claude-sonnet-4-6"
    s.ai_anthropic_max_tokens = 8096
    s.ai_anthropic_timeout_seconds = 60
    return s


def _svc(*, openai_key: str | None = None, anthropic_key: str | None = None) -> AIProviderReadinessService:
    with patch(_SVC_MODULE, return_value=_mock_settings(openai_key=openai_key, anthropic_key=anthropic_key)):
        return AIProviderReadinessService()


# ---------------------------------------------------------------------------
# 1. fake → available, configured=True
# ---------------------------------------------------------------------------


def test_fake_provider_available() -> None:
    """fake provider는 항상 status='available', configured=True."""
    svc = _svc()
    status = svc.get_provider_status("fake")
    assert status is not None
    assert status.status == "available"
    assert status.configured is True


# ---------------------------------------------------------------------------
# 2. fake → missing_settings 빈 목록
# ---------------------------------------------------------------------------


def test_fake_missing_settings_empty() -> None:
    """fake provider는 missing_settings가 빈 목록이다."""
    svc = _svc()
    status = svc.get_provider_status("fake")
    assert status is not None
    assert status.missing_settings == []


# ---------------------------------------------------------------------------
# 3. openai api_key 없음 → missing_config
# ---------------------------------------------------------------------------


def test_openai_no_key_missing_config() -> None:
    """AI_OPENAI_API_KEY 없으면 status='missing_config', configured=False."""
    svc = _svc(openai_key=None)
    status = svc.get_provider_status("openai")
    assert status is not None
    assert status.status == "missing_config"
    assert status.configured is False


# ---------------------------------------------------------------------------
# 4. openai api_key 있음 → available
# ---------------------------------------------------------------------------


def test_openai_with_key_available() -> None:
    """AI_OPENAI_API_KEY가 있으면 status='available', configured=True."""
    svc = _svc(openai_key="sk-test-key")
    status = svc.get_provider_status("openai")
    assert status is not None
    assert status.status == "available"
    assert status.configured is True


# ---------------------------------------------------------------------------
# 5. openai api_key 없음 → missing_settings=["AI_OPENAI_API_KEY"]
# ---------------------------------------------------------------------------


def test_openai_no_key_missing_settings_list() -> None:
    """API key 없으면 missing_settings에 'AI_OPENAI_API_KEY'가 포함된다."""
    svc = _svc(openai_key=None)
    status = svc.get_provider_status("openai")
    assert status is not None
    assert "AI_OPENAI_API_KEY" in status.missing_settings


# ---------------------------------------------------------------------------
# 6. openai api_key 있음 → missing_settings 빈 목록
# ---------------------------------------------------------------------------


def test_openai_with_key_missing_settings_empty() -> None:
    """API key가 있으면 missing_settings는 빈 목록이다."""
    svc = _svc(openai_key="sk-real-key")
    status = svc.get_provider_status("openai")
    assert status is not None
    assert status.missing_settings == []


# ---------------------------------------------------------------------------
# 7. anthropic api_key 없음 → missing_config
# ---------------------------------------------------------------------------


def test_anthropic_no_key_missing_config() -> None:
    """AI_ANTHROPIC_API_KEY 없으면 status='missing_config', configured=False."""
    svc = _svc(anthropic_key=None)
    status = svc.get_provider_status("anthropic")
    assert status is not None
    assert status.status == "missing_config"
    assert status.configured is False


# ---------------------------------------------------------------------------
# 8. anthropic api_key 있음 → available
# ---------------------------------------------------------------------------


def test_anthropic_with_key_available() -> None:
    """AI_ANTHROPIC_API_KEY가 있으면 status='available', configured=True."""
    svc = _svc(anthropic_key="sk-ant-test")
    status = svc.get_provider_status("anthropic")
    assert status is not None
    assert status.status == "available"
    assert status.configured is True


# ---------------------------------------------------------------------------
# 9. anthropic api_key 없음 → missing_settings=["AI_ANTHROPIC_API_KEY"]
# ---------------------------------------------------------------------------


def test_anthropic_no_key_missing_settings_list() -> None:
    """API key 없으면 missing_settings에 'AI_ANTHROPIC_API_KEY'가 포함된다."""
    svc = _svc(anthropic_key=None)
    status = svc.get_provider_status("anthropic")
    assert status is not None
    assert "AI_ANTHROPIC_API_KEY" in status.missing_settings


# ---------------------------------------------------------------------------
# 10. anthropic api_key 있음 → missing_settings 빈 목록
# ---------------------------------------------------------------------------


def test_anthropic_with_key_missing_settings_empty() -> None:
    """API key가 있으면 missing_settings는 빈 목록이다."""
    svc = _svc(anthropic_key="sk-ant-real")
    status = svc.get_provider_status("anthropic")
    assert status is not None
    assert status.missing_settings == []


# ---------------------------------------------------------------------------
# 11. 알 수 없는 provider → None
# ---------------------------------------------------------------------------


def test_unknown_provider_returns_none() -> None:
    """알 수 없는 provider 이름이면 get_provider_status()는 None을 반환한다."""
    svc = _svc()
    assert svc.get_provider_status("banana-llm") is None
    assert svc.get_provider_status("") is None
    assert svc.get_provider_status("gpt-5") is None


# ---------------------------------------------------------------------------
# 12. list_provider_statuses() → 3개 항목, 순서 확인
# ---------------------------------------------------------------------------


def test_list_provider_statuses_count_and_order() -> None:
    """list_provider_statuses()는 fake, openai, anthropic 순으로 3개를 반환한다."""
    svc = _svc()
    statuses = svc.list_provider_statuses()
    assert len(statuses) == 3
    names = [s.provider for s in statuses]
    assert names == ["fake", "openai", "anthropic"]


# ---------------------------------------------------------------------------
# 13. GET /api/v1/ai-analysis/providers → 200, 3개 항목
# ---------------------------------------------------------------------------


async def test_api_list_providers_returns_200() -> None:
    """GET /api/v1/ai-analysis/providers는 200과 함께 3개 항목을 반환한다."""
    with patch(_SVC_MODULE, return_value=_mock_settings()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/ai-analysis/providers")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 3
    providers = [item["provider"] for item in data]
    assert "fake" in providers
    assert "openai" in providers
    assert "anthropic" in providers


# ---------------------------------------------------------------------------
# 14. GET /api/v1/ai-analysis/providers/fake → 200, available
# ---------------------------------------------------------------------------


async def test_api_get_fake_provider() -> None:
    """GET /api/v1/ai-analysis/providers/fake는 200과 available 상태를 반환한다."""
    with patch(_SVC_MODULE, return_value=_mock_settings()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/ai-analysis/providers/fake")

    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "fake"
    assert data["status"] == "available"
    assert data["configured"] is True
    assert data["implemented"] is True


# ---------------------------------------------------------------------------
# 15. GET /api/v1/ai-analysis/providers/openai (no key) → 200, missing_config
# ---------------------------------------------------------------------------


async def test_api_get_openai_no_key() -> None:
    """GET /api/v1/ai-analysis/providers/openai — api_key 없으면 missing_config."""
    with patch(_SVC_MODULE, return_value=_mock_settings(openai_key=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/ai-analysis/providers/openai")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "missing_config"
    assert data["configured"] is False
    assert "AI_OPENAI_API_KEY" in data["missing_settings"]


# ---------------------------------------------------------------------------
# 16. GET /api/v1/ai-analysis/providers/anthropic (no key) → 200, missing_config
# ---------------------------------------------------------------------------


async def test_api_get_anthropic_no_key() -> None:
    """GET /api/v1/ai-analysis/providers/anthropic — api_key 없으면 missing_config."""
    with patch(_SVC_MODULE, return_value=_mock_settings(anthropic_key=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/ai-analysis/providers/anthropic")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "missing_config"
    assert data["configured"] is False
    assert "AI_ANTHROPIC_API_KEY" in data["missing_settings"]


# ---------------------------------------------------------------------------
# 17. GET /api/v1/ai-analysis/providers/unknown-llm → 404
# ---------------------------------------------------------------------------


async def test_api_get_unknown_provider_404() -> None:
    """알 수 없는 provider_name이면 404를 반환한다."""
    with patch(_SVC_MODULE, return_value=_mock_settings()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/ai-analysis/providers/unknown-llm")

    assert resp.status_code == 404
    assert "unknown-llm" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 18. fake → implemented=True
# ---------------------------------------------------------------------------


def test_fake_implemented_true() -> None:
    """fake provider는 implemented=True다."""
    svc = _svc()
    status = svc.get_provider_status("fake")
    assert status is not None
    assert status.implemented is True


# ---------------------------------------------------------------------------
# 19. openai → implemented=True
# ---------------------------------------------------------------------------


def test_openai_implemented_true() -> None:
    """openai provider는 implemented=True다."""
    svc = _svc()
    status = svc.get_provider_status("openai")
    assert status is not None
    assert status.implemented is True


# ---------------------------------------------------------------------------
# 20. anthropic → implemented=True
# ---------------------------------------------------------------------------


def test_anthropic_implemented_true() -> None:
    """anthropic provider는 implemented=True다."""
    svc = _svc()
    status = svc.get_provider_status("anthropic")
    assert status is not None
    assert status.implemented is True


# ---------------------------------------------------------------------------
# 21. default_model 필드 확인
# ---------------------------------------------------------------------------


def test_default_model_fields() -> None:
    """각 provider의 default_model이 설정값과 일치한다."""
    mock_s = _mock_settings()
    with patch(_SVC_MODULE, return_value=mock_s):
        svc = AIProviderReadinessService()

    fake_s = svc.get_provider_status("fake")
    openai_s = svc.get_provider_status("openai")
    anthropic_s = svc.get_provider_status("anthropic")

    assert fake_s.default_model == "fake-1.0"
    assert openai_s.default_model == mock_s.ai_openai_model
    assert anthropic_s.default_model == mock_s.ai_anthropic_model


# ---------------------------------------------------------------------------
# 22. note 필드 — api_key 있을 때 None, 없을 때 문자열
# ---------------------------------------------------------------------------


def test_note_field_when_key_present() -> None:
    """api_key가 있으면 note가 None이다."""
    svc = _svc(openai_key="sk-present", anthropic_key="sk-ant-present")
    assert svc.get_provider_status("openai").note is None
    assert svc.get_provider_status("anthropic").note is None


def test_note_field_when_key_missing() -> None:
    """api_key가 없으면 note가 비어있지 않은 문자열이다."""
    svc = _svc(openai_key=None, anthropic_key=None)
    openai_note = svc.get_provider_status("openai").note
    anthropic_note = svc.get_provider_status("anthropic").note
    assert isinstance(openai_note, str) and len(openai_note) > 0
    assert isinstance(anthropic_note, str) and len(anthropic_note) > 0


# ---------------------------------------------------------------------------
# 보조 — AIProviderStatusRead 구조 검증
# ---------------------------------------------------------------------------


def test_status_read_schema_fields() -> None:
    """AIProviderStatusRead가 필요한 모든 필드를 가진다."""
    item = AIProviderStatusRead(
        provider="fake",
        implemented=True,
        configured=True,
        default_model="fake-1.0",
        missing_settings=[],
        status="available",
        note=None,
    )
    assert item.provider == "fake"
    assert item.status == "available"
    assert item.missing_settings == []
