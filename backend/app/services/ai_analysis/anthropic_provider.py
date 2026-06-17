"""AnthropicAnalysisProvider — httpx 기반 Anthropic Messages API 구현 (C-2.7.2/C-2.7.5).

Anthropic Claude Messages API (POST /v1/messages)를 사용한다.
SDK 의존성 없이 httpx.AsyncClient로 직접 HTTP 호출한다.

참고:
  - Endpoint    : POST https://api.anthropic.com/v1/messages
  - Headers     : x-api-key, anthropic-version, content-type
  - Request     : {"model": "...", "max_tokens": N,
                   "messages": [{"role": "user", "content": "prompt"}]}
  - Response    : {"content": [{"type": "text", "text": "..."}],
                   "model": "...",
                   "stop_reason": "end_turn" | "max_tokens" | "stop_sequence" | "tool_use",
                   "usage": {"input_tokens": N, "output_tokens": M}}

finish_reason 매핑:
  end_turn      → "stop"
  max_tokens    → "length"
  stop_sequence → "stop"
  tool_use      → "tool_use"
  기타          → 원본 값 그대로

에러 처리:
  - 401/403        → retryable=False (인증 문제)
  - 429            → retryable=True  (rate limit)
  - 5xx            → retryable=True  (서버 오류)
  - httpx timeout  → retryable=True
  - httpx network  → retryable=True
  - malformed JSON → retryable=False
  - text 없음      → retryable=False
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.services.ai_analysis.base import AnalysisProvider
from app.services.ai_analysis.schemas import AnalysisProviderError, AnalysisProviderResult

logger = logging.getLogger(__name__)

_ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_PROVIDER_NAME = "anthropic"

# stop_reason → finish_reason 매핑 테이블
_STOP_REASON_MAP: dict[str, str] = {
    "end_turn": "stop",
    "max_tokens": "length",
    "stop_sequence": "stop",
}


def _extract_text(content: list[dict[str, Any]]) -> str:
    """content 배열에서 첫 번째 type=text 블록의 텍스트를 추출한다."""
    for block in content:
        if block.get("type") == "text":
            return block.get("text", "")
    return ""


def _map_finish_reason(stop_reason: str | None) -> str:
    """Anthropic stop_reason을 표준 finish_reason 문자열로 변환한다."""
    if not stop_reason:
        return "unknown"
    return _STOP_REASON_MAP.get(stop_reason, stop_reason)


def _parse_usage(usage: dict[str, Any] | None) -> tuple[int | None, int | None, int | None]:
    """usage dict에서 (prompt_tokens, completion_tokens, total_tokens)를 반환한다.

    Anthropic는 total_tokens를 제공하지 않으므로 input + output으로 계산한다.
    """
    if not usage:
        return None, None, None
    input_t = usage.get("input_tokens")
    output_t = usage.get("output_tokens")
    total = None
    if input_t is not None and output_t is not None:
        total = int(input_t) + int(output_t)
    return (
        int(input_t) if input_t is not None else None,
        int(output_t) if output_t is not None else None,
        total,
    )


class AnthropicAnalysisProvider(AnalysisProvider):
    """Anthropic Messages API를 httpx로 직접 호출하는 provider.

    API key는 생성 시점에 주입받는다. key가 없으면 analyze() 호출 시
    AnalysisProviderError(retryable=False)를 발생시킨다.
    """

    def __init__(
        self,
        api_key: str | None,
        default_model: str,
        default_timeout_seconds: int,
        max_tokens: int,
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._default_timeout_seconds = default_timeout_seconds
        self._max_tokens = max_tokens

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
                message=(
                    "Anthropic API key is not configured. "
                    "Set AI_ANTHROPIC_API_KEY in environment."
                ),
                retryable=False,
            )

        used_model = model or self._default_model
        timeout = float(timeout_seconds or self._default_timeout_seconds)

        request_body: dict[str, Any] = {
            "model": used_model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        t_start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    _ANTHROPIC_MESSAGES_URL,
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": _ANTHROPIC_VERSION,
                        "content-type": "application/json",
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

        return self._handle_response(response, used_model, latency_ms)

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    def _handle_response(
        self,
        response: httpx.Response,
        used_model: str,
        latency_ms: int,
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
        raw_content = body.get("content")
        if not raw_content or not isinstance(raw_content, list):
            raise AnalysisProviderError(
                provider=_PROVIDER_NAME,
                message=(
                    f"Unexpected response structure: missing 'content' array. "
                    f"body={body!r}"
                ),
                retryable=False,
                status_code=status_code,
                raw=body,
            )

        text = _extract_text(raw_content)
        if not text:
            raise AnalysisProviderError(
                provider=_PROVIDER_NAME,
                message="Response content contained no text block.",
                retryable=False,
                status_code=status_code,
                raw=body,
            )

        finish_reason = _map_finish_reason(body.get("stop_reason"))
        prompt_tokens, completion_tokens, total_tokens = _parse_usage(body.get("usage"))

        # Anthropic returns the resolved model name (e.g. "claude-sonnet-4-6-20250717")
        actual_model = body.get("model") or used_model

        return AnalysisProviderResult(
            provider=_PROVIDER_NAME,
            model=actual_model,
            content=text,
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

        error_type = ""
        error_msg = ""

        if isinstance(raw, dict):
            err = raw.get("error") or {}
            if isinstance(err, dict):
                error_type = err.get("type") or ""
                error_msg = err.get("message") or ""

        if not error_msg:
            error_msg = response.text[:300] if response.text else f"HTTP {status_code}"

        # error.type을 메시지에 포함해 진단 정보를 풍부하게 한다
        message = (
            f"HTTP {status_code} {error_type}: {error_msg}"
            if error_type
            else f"HTTP {status_code}: {error_msg}"
        )

        raise AnalysisProviderError(
            provider=_PROVIDER_NAME,
            message=message,
            retryable=retryable,
            status_code=status_code,
            raw=raw,
        )
