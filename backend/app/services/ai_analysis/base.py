"""AI Analysis Provider 공통 인터페이스.

BrokerClient와 동일한 패턴: ABC로 계약을 정의하고,
구현체(FakeAnalysisProvider, OpenAIAnalysisProvider, AnthropicAnalysisProvider)가 상속한다.

호출 예시:
    provider = get_analysis_provider("fake")
    result = await provider.analyze(prompt)
    # result.content, result.total_tokens, result.latency_ms 사용
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.services.ai_analysis.schemas import AnalysisProviderResult


class AnalysisProvider(ABC):
    """LLM provider 공통 인터페이스.

    각 구현체는 이 클래스를 상속하고 analyze()를 구현한다.
    호출자는 구체적인 provider를 알 필요 없이 이 인터페이스만 사용한다.
    """

    @abstractmethod
    async def analyze(
        self,
        prompt: str,
        *,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> AnalysisProviderResult:
        """prompt를 분석하고 결과를 반환한다.

        Args:
            prompt: LLM에 전달할 전체 프롬프트 (system + user 내용 포함).
            model: 사용할 모델 이름. None이면 provider 기본값 사용.
            timeout_seconds: 요청 타임아웃(초). None이면 provider 기본값 사용.

        Returns:
            AnalysisProviderResult

        Raises:
            AnalysisProviderError: API 호출 실패, 타임아웃, rate limit 등.
        """
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """이 provider의 식별자 문자열을 반환한다. 예: "fake", "openai", "anthropic"."""
        ...

    @abstractmethod
    def default_model(self) -> str:
        """model 인자가 None일 때 사용할 기본 모델 이름을 반환한다."""
        ...
