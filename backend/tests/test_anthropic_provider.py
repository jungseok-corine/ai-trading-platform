"""AnthropicAnalysisProvider 테스트 (C-2.7.2).

실제 네트워크 호출 없음 — httpx.AsyncClient.post를 AsyncMock으로 대체한다.

검증 항목:
  1.  성공 응답 파싱 (content, model)
  2.  token usage 파싱 (input/output/total_tokens)
  3.  finish_reason — end_turn → "stop"
  4.  finish_reason — max_tokens → "length"
  5.  finish_reason — stop_sequence → "stop"
  6.  API key 없음 → AnalysisProviderError(retryable=False)
  7.  401 → retryable=False
  8.  403 → retryable=False
  9.  429 → retryable=True
  10. 500 → retryable=True
  11. timeout → retryable=True
  12. network error → retryable=True
  13. malformed JSON → retryable=False
  14. content 배열 없는 응답 → retryable=False
  15. text content 없는 응답 → retryable=False
  16. factory가 anthropic provider를 반환
  17. provider_name() == "anthropic"
  18. default_model()이 settings.ai_anthropic_model과 일치
  19. model override 적용 확인
  20. 요청 헤더 확인 (x-api-key, anthropic-version)
"""
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.ai_analysis import AnalysisProviderError, get_analysis_provider
from app.services.ai_analysis.anthropic_provider import AnthropicAnalysisProvider
from app.services.ai_analysis.schemas import AnalysisProviderResult

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_FAKE_KEY = "sk-ant-test-fake-key"
_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_TIMEOUT = 30
_MAX_TOKENS = 8096


def _make_provider(api_key: str | None = _FAKE_KEY) -> AnthropicAnalysisProvider:
    return AnthropicAnalysisProvider(
        api_key=api_key,
        default_model=_DEFAULT_MODEL,
        default_timeout_seconds=_DEFAULT_TIMEOUT,
        max_tokens=_MAX_TOKENS,
    )


def _ok_body(
    text: str = "Analysis result from Claude.",
    model: str = "claude-sonnet-4-6-20250717",
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    }


def _mock_response(
    status_code: int = 200,
    body: dict[str, Any] | None = None,
    text: str | None = None,
) -> MagicMock:
    """httpx.Response처럼 동작하는 MagicMock."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    if body is not None:
        resp.json.return_value = body
        resp.text = json.dumps(body)
    elif text is not None:
        resp.json.side_effect = ValueError("not json")
        resp.text = text
    else:
        resp.json.return_value = {}
        resp.text = ""
    return resp


# ---------------------------------------------------------------------------
# 1. 성공 응답 파싱
# ---------------------------------------------------------------------------


async def test_anthropic_provider_success_content() -> None:
    """200 OK 응답에서 content와 model을 올바르게 추출한다."""
    provider = _make_provider()
    body = _ok_body(text="Strategy analysis complete.")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_mock_response(200, body)):
        result = await provider.analyze("Analyze this strategy.")

    assert isinstance(result, AnalysisProviderResult)
    assert result.provider == "anthropic"
    assert result.content == "Strategy analysis complete."
    assert result.model == "claude-sonnet-4-6-20250717"


# ---------------------------------------------------------------------------
# 2. token usage 파싱
# ---------------------------------------------------------------------------


async def test_anthropic_provider_token_usage() -> None:
    """usage 필드에서 prompt/completion/total_tokens를 올바르게 추출한다."""
    provider = _make_provider()
    body = _ok_body(input_tokens=120, output_tokens=80)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_mock_response(200, body)):
        result = await provider.analyze("Analyze.")

    assert result.prompt_tokens == 120
    assert result.completion_tokens == 80
    assert result.total_tokens == 200   # input + output


# ---------------------------------------------------------------------------
# 3. finish_reason — end_turn → "stop"
# ---------------------------------------------------------------------------


async def test_anthropic_finish_reason_end_turn() -> None:
    """stop_reason='end_turn' → finish_reason='stop'."""
    provider = _make_provider()
    body = _ok_body(stop_reason="end_turn")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_mock_response(200, body)):
        result = await provider.analyze("Analyze.")

    assert result.finish_reason == "stop"


# ---------------------------------------------------------------------------
# 4. finish_reason — max_tokens → "length"
# ---------------------------------------------------------------------------


async def test_anthropic_finish_reason_max_tokens() -> None:
    """stop_reason='max_tokens' → finish_reason='length'."""
    provider = _make_provider()
    body = _ok_body(stop_reason="max_tokens")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_mock_response(200, body)):
        result = await provider.analyze("Analyze.")

    assert result.finish_reason == "length"


# ---------------------------------------------------------------------------
# 5. finish_reason — stop_sequence → "stop"
# ---------------------------------------------------------------------------


async def test_anthropic_finish_reason_stop_sequence() -> None:
    """stop_reason='stop_sequence' → finish_reason='stop'."""
    provider = _make_provider()
    body = _ok_body(stop_reason="stop_sequence")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_mock_response(200, body)):
        result = await provider.analyze("Analyze.")

    assert result.finish_reason == "stop"


# ---------------------------------------------------------------------------
# 6. API key 없음 → AnalysisProviderError(retryable=False)
# ---------------------------------------------------------------------------


async def test_anthropic_no_api_key_raises_error() -> None:
    """api_key=None이면 네트워크 호출 없이 AnalysisProviderError를 발생시킨다."""
    provider = _make_provider(api_key=None)

    with pytest.raises(AnalysisProviderError) as exc_info:
        await provider.analyze("Analyze.")

    err = exc_info.value
    assert err.provider == "anthropic"
    assert err.retryable is False
    assert "api key" in err.message.lower()


# ---------------------------------------------------------------------------
# 7. 401 → retryable=False
# ---------------------------------------------------------------------------


async def test_anthropic_401_not_retryable() -> None:
    """HTTP 401 → AnalysisProviderError(retryable=False)."""
    provider = _make_provider()
    error_body = {
        "type": "error",
        "error": {"type": "authentication_error", "message": "invalid x-api-key"},
    }

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_mock_response(401, error_body),
    ):
        with pytest.raises(AnalysisProviderError) as exc_info:
            await provider.analyze("Analyze.")

    err = exc_info.value
    assert err.retryable is False
    assert err.status_code == 401
    assert "401" in err.message


# ---------------------------------------------------------------------------
# 8. 403 → retryable=False
# ---------------------------------------------------------------------------


async def test_anthropic_403_not_retryable() -> None:
    """HTTP 403 → AnalysisProviderError(retryable=False)."""
    provider = _make_provider()
    error_body = {
        "type": "error",
        "error": {"type": "permission_error", "message": "Permission denied."},
    }

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_mock_response(403, error_body),
    ):
        with pytest.raises(AnalysisProviderError) as exc_info:
            await provider.analyze("Analyze.")

    err = exc_info.value
    assert err.retryable is False
    assert err.status_code == 403


# ---------------------------------------------------------------------------
# 9. 429 → retryable=True
# ---------------------------------------------------------------------------


async def test_anthropic_429_retryable() -> None:
    """HTTP 429 → AnalysisProviderError(retryable=True)."""
    provider = _make_provider()
    error_body = {
        "type": "error",
        "error": {"type": "rate_limit_error", "message": "Rate limit exceeded."},
    }

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_mock_response(429, error_body),
    ):
        with pytest.raises(AnalysisProviderError) as exc_info:
            await provider.analyze("Analyze.")

    err = exc_info.value
    assert err.retryable is True
    assert err.status_code == 429


# ---------------------------------------------------------------------------
# 10. 500 → retryable=True
# ---------------------------------------------------------------------------


async def test_anthropic_500_retryable() -> None:
    """HTTP 500 → AnalysisProviderError(retryable=True)."""
    provider = _make_provider()

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_mock_response(500, text="Internal Server Error"),
    ):
        with pytest.raises(AnalysisProviderError) as exc_info:
            await provider.analyze("Analyze.")

    err = exc_info.value
    assert err.retryable is True
    assert err.status_code == 500


# ---------------------------------------------------------------------------
# 11. timeout → retryable=True
# ---------------------------------------------------------------------------


async def test_anthropic_timeout_retryable() -> None:
    """httpx.TimeoutException → AnalysisProviderError(retryable=True)."""
    provider = _make_provider()

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("timed out"),
    ):
        with pytest.raises(AnalysisProviderError) as exc_info:
            await provider.analyze("Analyze.")

    err = exc_info.value
    assert err.retryable is True
    assert err.status_code is None


# ---------------------------------------------------------------------------
# 12. network error → retryable=True
# ---------------------------------------------------------------------------


async def test_anthropic_network_error_retryable() -> None:
    """httpx.RequestError (network failure) → AnalysisProviderError(retryable=True)."""
    provider = _make_provider()

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("connection refused"),
    ):
        with pytest.raises(AnalysisProviderError) as exc_info:
            await provider.analyze("Analyze.")

    err = exc_info.value
    assert err.retryable is True


# ---------------------------------------------------------------------------
# 13. malformed JSON → retryable=False
# ---------------------------------------------------------------------------


async def test_anthropic_malformed_json_not_retryable() -> None:
    """200이지만 JSON 파싱 실패 → AnalysisProviderError(retryable=False)."""
    provider = _make_provider()

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_mock_response(200, text="not-valid-json"),
    ):
        with pytest.raises(AnalysisProviderError) as exc_info:
            await provider.analyze("Analyze.")

    err = exc_info.value
    assert err.retryable is False


# ---------------------------------------------------------------------------
# 14. content 배열 없는 응답 → retryable=False
# ---------------------------------------------------------------------------


async def test_anthropic_missing_content_array_not_retryable() -> None:
    """content 필드가 없는 응답 → AnalysisProviderError(retryable=False)."""
    provider = _make_provider()
    bad_body = {"id": "msg_x", "type": "message", "role": "assistant", "model": "claude-sonnet-4-6"}

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_mock_response(200, bad_body),
    ):
        with pytest.raises(AnalysisProviderError) as exc_info:
            await provider.analyze("Analyze.")

    err = exc_info.value
    assert err.retryable is False


# ---------------------------------------------------------------------------
# 15. text content 없는 응답 → retryable=False
# ---------------------------------------------------------------------------


async def test_anthropic_empty_text_content_not_retryable() -> None:
    """content 배열은 있지만 type=text 블록이 없음 → AnalysisProviderError(retryable=False)."""
    provider = _make_provider()
    body = {
        "id": "msg_x",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-6",
        "content": [{"type": "tool_use", "id": "tu_1", "name": "some_tool", "input": {}}],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_mock_response(200, body),
    ):
        with pytest.raises(AnalysisProviderError) as exc_info:
            await provider.analyze("Analyze.")

    err = exc_info.value
    assert err.retryable is False


# ---------------------------------------------------------------------------
# 16. factory가 anthropic provider를 반환
# ---------------------------------------------------------------------------


def test_factory_returns_anthropic_provider() -> None:
    """get_analysis_provider('anthropic')가 AnthropicAnalysisProvider를 반환한다."""
    provider = get_analysis_provider("anthropic")
    assert isinstance(provider, AnthropicAnalysisProvider)
    assert provider.provider_name() == "anthropic"


# ---------------------------------------------------------------------------
# 17. provider_name()
# ---------------------------------------------------------------------------


def test_anthropic_provider_name() -> None:
    """provider_name() == 'anthropic'."""
    assert _make_provider().provider_name() == "anthropic"


# ---------------------------------------------------------------------------
# 18. default_model()이 settings와 일치
# ---------------------------------------------------------------------------


def test_anthropic_default_model_matches_settings() -> None:
    """factory가 반환하는 provider의 default_model이 settings.ai_anthropic_model과 일치한다."""
    from app.core.config import get_settings
    s = get_settings()
    provider = get_analysis_provider("anthropic")
    assert provider.default_model() == s.ai_anthropic_model


# ---------------------------------------------------------------------------
# 19. model override 적용
# ---------------------------------------------------------------------------


async def test_anthropic_model_override() -> None:
    """analyze(model='claude-opus-4-8') 시 요청 body의 model 필드가 override된다."""
    provider = _make_provider()
    override_model = "claude-opus-4-8"
    body = _ok_body(model=override_model)

    captured: dict = {}

    async def _fake_post(url: str, *, headers=None, json=None, **kwargs):
        captured.update(json or {})
        return _mock_response(200, body)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_fake_post):
        result = await provider.analyze("Analyze.", model=override_model)

    assert captured.get("model") == override_model
    assert result.model == override_model


# ---------------------------------------------------------------------------
# 20. 요청 헤더 확인
# ---------------------------------------------------------------------------


async def test_anthropic_request_headers() -> None:
    """요청 헤더에 x-api-key, anthropic-version이 포함된다."""
    provider = _make_provider(api_key="sk-ant-my-key")
    body = _ok_body()

    captured_headers: dict = {}

    async def _fake_post(url: str, *, headers=None, json=None, **kwargs):
        captured_headers.update(headers or {})
        return _mock_response(200, body)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_fake_post):
        await provider.analyze("Analyze.")

    assert captured_headers.get("x-api-key") == "sk-ant-my-key"
    assert "anthropic-version" in captured_headers
    assert captured_headers.get("content-type") == "application/json"
