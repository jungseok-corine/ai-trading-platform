"""OpenAIAnalysisProvider — httpx 기반 OpenAI Responses API 구현 (C-2.7.1).

OpenAI Responses API (POST /v1/responses)를 사용한다.
SDK 의존성 없이 httpx.AsyncClient로 직접 HTTP 호출한다.

참고:
  - Endpoint : POST https://api.openai.com/v1/responses
  - Request  : {"model": "...", "input": "prompt text"}
  - Response : {"output": [{"content": [{"type": "output_text", "text": "..."}]}],
                "usage": {"input_tokens": N, "output_tokens": M, "total_tokens": L},
                "status": "completed" | "incomplete" | "failed"}

에러 처리:
  - 401/403        → retryable=False (인증 문제)
  - 429            → retryable=True  (rate limit)
  - 5xx            → retryable=True  (서버 오류)
  - httpx timeout  → retryable=True
  - malformed JSON → retryable=False
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.services.ai_analysis.base import AnalysisProvider
from app.services.ai_analysis.schemas import AnalysisProviderError, AnalysisProviderResult

logger = logging.getLogger(__name__)

_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
_PROVIDER_NAME = "openai"


def _extract_text(output: list[dict[str, Any]]) -> str:
    """output 배열에서 첫 번째 output_text content를 추출한다."""
    for item in output:
        for block in item.get("content", []):
            if block.get("type") == "output_text":
                return block.get("text", "")
    return ""


def _extract_finish_reason(response_body: dict[str, Any]) -> str:
    """응답 status를 OpenAI finish_reason 규칙으로 변환한다."""
    status = response_body.get("status", "")
    if status == "completed":
        return "stop"
    if status == "incomplete":
        details = response_body.get("incomplete_details") or {}
        reason = details.get("reason", "")
        if reason == "max_output_tokens":
            return "length"
        return f"incomplete:{reason}" if reason else "incomplete"
    return status or "unknown"


def _parse_usage(usage: dict[str, Any] | None) -> tuple[int | None, int | None, int | None]:
    """usage dict에서 (prompt_tokens, completion_tokens, total_tokens)를 반환한다."""
    if not usage:
        return None, None, None
    prompt = usage.get("input_tokens")
    completion = usage.get("output_tokens")
    total = usage.get("total_tokens")
    # total이 없으면 직접 계산
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    return (
        int(prompt) if prompt is not None else None,
        int(completion) if completion is not None else None,
        int(total) if total is not None else None,
    )


class OpenAIAnalysisProvider(AnalysisProvider):
    """OpenAI Responses API를 httpx로 직접 호출하는 provider.

    API key는 생성 시점에 주입받는다. key가 없으면 analyze() 호출 시
    AnalysisProviderError(retryable=False)를 발생시킨다.
    """

    def __init__(self, api_key: str | None, default_model: str, default_timeout_seconds: int) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._default_timeout_seconds = default_timeout_seconds

    # ------------------------------------------------------------------
    # AnalysisProvider interface
    # ------------------------------------------------------------------

    def provider_name(self) -> str:
        return _PROVIDER_NAME

    def default_model(self) -> str:
        return self._default_model

    async def analyze(
        self,
        prompt: str,
        *,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> AnalysisProviderResult:
        if not self._api_key:
            raise AnalysisProviderError(
                provider=_PROVIDER_NAME,
                message="OpenAI API key is not configured. Set AI_OPENAI_API_KEY in environment.",
                retryable=False,
            )

        used_model = model or self._default_model
        timeout = float(timeout_seconds or self._default_timeout_seconds)

        request_body: dict[str, Any] = {
            "model": used_model,
            "input": prompt,
        }

        t_start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    _OPENAI_RESPONSES_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                )
        except httpx.TimeoutException as exc:
            raise AnalysisProviderError(
                provider=_PROVIDER_NAME,
                message=f"Request timed out after {timeout}s: {exc}",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AnalysisProviderError(
                provider=_PROVIDER_NAME,
                message=f"Network error: {exc}",
                retryable=True,
            ) from exc

        latency_ms = int((time.monotonic() - t_start) * 1000)

        return self._handle_response(response, used_model, latency_ms, request_body)

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    def _handle_response(
        self,
        response: httpx.Response,
        used_model: str,
        latency_ms: int,
        request_body: dict[str, Any],
    ) -> AnalysisProviderResult:
        status_code = response.status_code

        # --- HTTP 에러 처리 ---
        if status_code in (401, 403):
            self._raise_http_error(response, status_code, retryable=False)

        if status_code == 429:
            self._raise_http_error(response, status_code, retryable=True)

        if status_code >= 500:
            self._raise_http_error(response, status_code, retryable=True)

        if status_code != 200:
            self._raise_http_error(response, status_code, retryable=False)

        # --- JSON 파싱 ---
        try:
            body: dict[str, Any] = response.json()
        except Exception as exc:
            raise AnalysisProviderError(
                provider=_PROVIDER_NAME,
                message=f"Malformed JSON response (status={status_code}): {exc}",
                retryable=False,
                status_code=status_code,
            ) from exc

        # --- 응답 구조 검증 ---
        output = body.get("output")
        if not output or not isinstance(output, list):
            raise AnalysisProviderError(
                provider=_PROVIDER_NAME,
                message=f"Unexpected response structure: missing 'output' array. body={body!r}",
                retryable=False,
                status_code=status_code,
                raw=body,
            )

        content = _extract_text(output)
        if not content:
            raise AnalysisProviderError(
                provider=_PROVIDER_NAME,
                message="Response output contained no text content.",
                retryable=False,
                status_code=status_code,
                raw=body,
            )

        finish_reason = _extract_finish_reason(body)
        prompt_tokens, completion_tokens, total_tokens = _parse_usage(body.get("usage"))

        # actual model may differ from requested (e.g. aliased models)
        actual_model = body.get("model") or used_model

        return AnalysisProviderResult(
            provider=_PROVIDER_NAME,
            model=actual_model,
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            raw=body,
        )

    def _raise_http_error(
        self,
        response: httpx.Response,
        status_code: int,
        *,
        retryable: bool,
    ) -> None:
        try:
            raw = response.json()
        except Exception:
            raw = None

        error_msg = ""
        if isinstance(raw, dict):
            err = raw.get("error") or {}
            error_msg = err.get("message", "") if isinstance(err, dict) else str(err)
        if not error_msg:
            error_msg = response.text[:300] if response.text else f"HTTP {status_code}"

        raise AnalysisProviderError(
            provider=_PROVIDER_NAME,
            message=f"HTTP {status_code}: {error_msg}",
            retryable=retryable,
            status_code=status_code,
            raw=raw,
        )
