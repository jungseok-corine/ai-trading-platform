"""OpenAIAnalysisProvider 테스트 (C-2.7.1).

실제 네트워크 호출 없음 — httpx.AsyncClient.post를 AsyncMock으로 대체한다.

검증 항목:
  1. 성공 응답 파싱 (content, model)
  2. token usage 파싱 (input/output/total_tokens)
  3. finish_reason — completed → "stop"
  4. finish_reason — incomplete/max_output_tokens → "length"
  5. API key 없음 → AnalysisProviderError(retryable=False)
  6. 401 → retryable=False
  7. 403 → retryable=False
  8. 429 → retryable=True
  9. 500 → retryable=True
  10. timeout → retryable=True
  11. malformed JSON → retryable=False
  12. output 배열 없는 응답 → retryable=False
  13. output에 text content 없는 응답 → retryable=False
  14. factory가 openai provider 반환
  15. provider_name() == "openai"
  16. default_model()이 settings.ai_openai_model과 일치
  17. model override 적용 확인
"""
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.ai_analysis import AnalysisProviderError, get_analysis_provider
from app.services.ai_analysis.openai_provider import OpenAIAnalysisProvider
from app.services.ai_analysis.schemas import AnalysisProviderResult

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_FAKE_KEY = "sk-test-fake-key"
_DEFAULT_MODEL = "gpt-4o"
_DEFAULT_TIMEOUT = 30


def _make_provider(api_key: str | None = _FAKE_KEY) -> OpenAIAnalysisProvider:
    return OpenAIAnalysisProvider(
        api_key=api_key,
        default_model=_DEFAULT_MODEL,
        default_timeout_seconds=_DEFAULT_TIMEOUT,
    )


def _ok_body(
    text: str = "Analysis result.",
    status: str = "completed",
    model: str = "gpt-4o-2024-08-06",
    input_tokens: int = 100,
    output_tokens: int = 50,
    total_tokens: int = 150,
    incomplete_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "resp_test",
        "object": "response",
        "model": model,
        "status": status,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
        "error": None,
    }
    if incomplete_details is not None:
        body["incomplete_details"] = incomplete_details
    return body


def _mock_response(
    status_code: int = 200,
    body: dict[str, Any] | None = None,
    text: str | None = None,
) -> MagicMock:
    """httpx.Response처럼 동작하는 MagicMock을 반환한다."""
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


async def test_openai_provider_success_content() -> None:
    """200 OK 응답에서 content를 올바르게 추출한다."""
    provider = _make_provider()
    body = _ok_body(text="Strategy looks bullish.")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_mock_response(200, body)):
        result = await provider.analyze("Analyze this strategy.")

    assert isinstance(result, AnalysisProviderResult)
    assert result.provider == "openai"
    assert result.content == "Strategy looks bullish."


# ---------------------------------------------------------------------------
# 2. token usage 파싱
# ---------------------------------------------------------------------------


async def test_openai_provider_token_usage() -> None:
    """usage 필드에서 prompt/completion/total_tokens를 올바르게 추출한다."""
    provider = _make_provider()
    body = _ok_body(input_tokens=120, output_tokens=80, total_tokens=200)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_mock_response(200, body)):
        result = await provider.analyze("Analyze.")

    assert result.prompt_tokens == 120
    assert result.completion_tokens == 80
    assert result.total_tokens == 200


# ---------------------------------------------------------------------------
# 3. finish_reason — completed → "stop"
# ---------------------------------------------------------------------------


async def test_openai_provider_finish_reason_stop() -> None:
    """status='completed' → finish_reason='stop'."""
    provider = _make_provider()
    body = _ok_body(status="completed")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_mock_response(200, body)):
        result = await provider.analyze("Analyze.")

    assert result.finish_reason == "stop"


# ---------------------------------------------------------------------------
# 4. finish_reason — incomplete → "length"
# ---------------------------------------------------------------------------


async def test_openai_provider_finish_reason_length() -> None:
    """status='incomplete', reason='max_output_tokens' → finish_reason='length'."""
    provider = _make_provider()
    body = _ok_body(status="incomplete", incomplete_details={"reason": "max_output_tokens"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_mock_response(200, body)):
        result = await provider.analyze("Analyze.")

    assert result.finish_reason == "length"


# ---------------------------------------------------------------------------
# 5. API key 없음 → AnalysisProviderError(retryable=False)
# ---------------------------------------------------------------------------


async def test_openai_provider_no_api_key_raises_error() -> None:
    """api_key=None이면 network 호출 없이 AnalysisProviderError를 발생시킨다."""
    provider = _make_provider(api_key=None)

    with pytest.raises(AnalysisProviderError) as exc_info:
        await provider.analyze("Analyze.")

    err = exc_info.value
    assert err.provider == "openai"
    assert err.retryable is False
    assert "api key" in err.message.lower()


# ---------------------------------------------------------------------------
# 6. 401 → retryable=False
# ---------------------------------------------------------------------------


async def test_openai_provider_401_not_retryable() -> None:
    """HTTP 401 → AnalysisProviderError(retryable=False)."""
    provider = _make_provider()
    error_body = {"error": {"message": "Incorrect API key.", "type": "invalid_request_error"}}

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
# 7. 403 → retryable=False
# ---------------------------------------------------------------------------


async def test_openai_provider_403_not_retryable() -> None:
    """HTTP 403 → AnalysisProviderError(retryable=False)."""
    provider = _make_provider()
    error_body = {"error": {"message": "Permission denied.", "type": "insufficient_quota"}}

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
# 8. 429 → retryable=True
# ---------------------------------------------------------------------------


async def test_openai_provider_429_retryable() -> None:
    """HTTP 429 → AnalysisProviderError(retryable=True)."""
    provider = _make_provider()
    error_body = {"error": {"message": "Rate limit exceeded.", "type": "rate_limit_error"}}

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
# 9. 500 → retryable=True
# ---------------------------------------------------------------------------


async def test_openai_provider_500_retryable() -> None:
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
# 10. timeout → retryable=True
# ---------------------------------------------------------------------------


async def test_openai_provider_timeout_retryable() -> None:
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
    assert "timed out" in err.message.lower() or "timeout" in err.message.lower()


# ---------------------------------------------------------------------------
# 11. malformed JSON → retryable=False
# ---------------------------------------------------------------------------


async def test_openai_provider_malformed_json_not_retryable() -> None:
    """200이지만 JSON 파싱 실패 → AnalysisProviderError(retryable=False)."""
    provider = _make_provider()

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_mock_response(200, text="not-json-at-all"),
    ):
        with pytest.raises(AnalysisProviderError) as exc_info:
            await provider.analyze("Analyze.")

    err = exc_info.value
    assert err.retryable is False


# ---------------------------------------------------------------------------
# 12. output 배열 없는 응답 → retryable=False
# ---------------------------------------------------------------------------


async def test_openai_provider_missing_output_not_retryable() -> None:
    """output 필드가 없거나 빈 응답 → AnalysisProviderError(retryable=False)."""
    provider = _make_provider()
    bad_body = {"id": "resp_x", "status": "completed", "usage": {}}

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
# 13. output에 text content 없는 응답 → retryable=False
# ---------------------------------------------------------------------------


async def test_openai_provider_empty_text_content_not_retryable() -> None:
    """output이 있지만 output_text가 비어 있음 → AnalysisProviderError(retryable=False)."""
    provider = _make_provider()
    body = {
        "id": "resp_x",
        "status": "completed",
        "model": "gpt-4o",
        "output": [{"type": "message", "role": "assistant", "content": []}],
        "usage": {"input_tokens": 10, "output_tokens": 0, "total_tokens": 10},
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
# 14. factory가 openai provider를 반환한다
# ---------------------------------------------------------------------------


def test_factory_returns_openai_provider() -> None:
    """get_analysis_provider('openai')가 OpenAIAnalysisProvider를 반환한다."""
    provider = get_analysis_provider("openai")
    assert isinstance(provider, OpenAIAnalysisProvider)
    assert provider.provider_name() == "openai"


# ---------------------------------------------------------------------------
# 15. provider_name()
# ---------------------------------------------------------------------------


def test_openai_provider_name() -> None:
    """provider_name() == 'openai'."""
    provider = _make_provider()
    assert provider.provider_name() == "openai"


# ---------------------------------------------------------------------------
# 16. default_model()이 settings와 일치
# ---------------------------------------------------------------------------


def test_openai_provider_default_model_matches_settings() -> None:
    """factory가 반환하는 provider의 default_model이 settings.ai_openai_model과 일치한다."""
    from app.core.config import get_settings
    s = get_settings()
    provider = get_analysis_provider("openai")
    assert provider.default_model() == s.ai_openai_model


# ---------------------------------------------------------------------------
# 17. model override 적용
# ---------------------------------------------------------------------------


async def test_openai_provider_model_override() -> None:
    """analyze(model='gpt-4-turbo') 시 요청 body의 model 필드가 override된다."""
    provider = _make_provider()
    override_model = "gpt-4-turbo"
    body = _ok_body(model=override_model)

    captured_kwargs: dict = {}

    async def _fake_post(url: str, *, headers=None, json=None, **kwargs):
        captured_kwargs.update(json or {})
        return _mock_response(200, body)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_fake_post):
        result = await provider.analyze("Analyze.", model=override_model)

    assert captured_kwargs.get("model") == override_model
    assert result.model == override_model
