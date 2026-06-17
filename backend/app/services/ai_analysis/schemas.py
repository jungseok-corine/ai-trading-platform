"""AI Analysis Provider 공통 데이터 모델.

실제 API 응답이나 DB 스키마와 분리된 순수 도메인 모델이다.
외부 라이브러리 의존 없이 dataclass만 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnalysisProviderResult:
    """LLM provider로부터 받은 분석 응답.

    provider/model 식별자가 포함되어 있으므로, 여러 provider의 응답을
    동일한 타입으로 다룰 수 있다.
    """

    provider: str                    # "fake" | "openai" | "anthropic"
    model: str                       # 실제 모델 식별자 (예: "gpt-4o", "claude-sonnet-4-6")
    content: str                     # LLM이 생성한 분석 텍스트
    prompt_tokens: int | None        # 입력 토큰 수 (추정치 포함)
    completion_tokens: int | None    # 출력 토큰 수 (추정치 포함)
    total_tokens: int | None         # 합계 (provider가 제공하지 않으면 직접 합산)
    latency_ms: int | None           # 응답 수신까지 소요 시간 (ms)
    finish_reason: str | None        # "stop" | "length" | "error" | provider별 값
    raw: dict | None                 # provider 원본 응답 (디버깅용)


class AnalysisProviderError(Exception):
    """LLM provider 호출 실패를 나타내는 예외.

    retryable=True이면 호출자가 재시도할 수 있다.
    retryable=False이면 재시도해도 동일하게 실패할 가능성이 높다.
    """

    def __init__(
        self,
        *,
        provider: str,
        message: str,
        retryable: bool = False,
        status_code: int | None = None,
        raw: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.message = message
        self.retryable = retryable
        self.status_code = status_code
        self.raw = raw

    def __repr__(self) -> str:
        return (
            f"AnalysisProviderError(provider={self.provider!r}, "
            f"message={self.message!r}, retryable={self.retryable}, "
            f"status_code={self.status_code})"
        )
