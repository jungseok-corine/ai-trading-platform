"""AI Analysis Provider factory.

get_analysis_provider()로 provider 이름을 받아 구현체를 반환한다.
현재 "fake"만 실제 반환하며, "openai"/"anthropic"은 구현 대기 상태다.

사용 예:
    provider = get_analysis_provider("fake")
    result = await provider.analyze(prompt)

향후 C-2.3 이후 단계에서:
    provider = get_analysis_provider("openai")    # OpenAIAnalysisProvider 반환
    provider = get_analysis_provider("anthropic")  # AnthropicAnalysisProvider 반환
"""
from __future__ import annotations

from app.services.ai_analysis.base import AnalysisProvider
from app.services.ai_analysis.fake import FakeAnalysisProvider

_SUPPORTED_PROVIDERS: frozenset[str] = frozenset({"fake", "openai", "anthropic"})
_IMPLEMENTED_PROVIDERS: frozenset[str] = frozenset({"fake"})


class ProviderNotImplementedError(NotImplementedError):
    """요청한 provider가 아직 구현되지 않았을 때 발생한다."""

    def __init__(self, provider_name: str) -> None:
        super().__init__(
            f"AI provider '{provider_name}' is not yet implemented. "
            f"Currently implemented: {', '.join(sorted(_IMPLEMENTED_PROVIDERS))}. "
            f"Supported (future): {', '.join(sorted(_SUPPORTED_PROVIDERS))}."
        )
        self.provider_name = provider_name


class UnknownProviderError(ValueError):
    """알 수 없는 provider 이름이 지정되었을 때 발생한다."""

    def __init__(self, provider_name: str) -> None:
        super().__init__(
            f"Unknown AI provider: '{provider_name}'. "
            f"Supported: {', '.join(sorted(_SUPPORTED_PROVIDERS))}."
        )
        self.provider_name = provider_name


def get_analysis_provider(provider_name: str) -> AnalysisProvider:
    """provider_name에 해당하는 AnalysisProvider 구현체를 반환한다.

    Args:
        provider_name: "fake" | "openai" | "anthropic"

    Returns:
        AnalysisProvider 구현체

    Raises:
        UnknownProviderError: 알 수 없는 provider 이름
        ProviderNotImplementedError: 알려진 provider이지만 아직 구현되지 않음
    """
    if provider_name not in _SUPPORTED_PROVIDERS:
        raise UnknownProviderError(provider_name)

    if provider_name == "fake":
        return FakeAnalysisProvider()

    # "openai", "anthropic" — 향후 C-2.4 이후에 구현
    raise ProviderNotImplementedError(provider_name)
