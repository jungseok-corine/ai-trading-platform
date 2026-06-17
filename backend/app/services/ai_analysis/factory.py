"""AI Analysis Provider factory.

get_analysis_provider()로 provider 이름을 받아 구현체를 반환한다.

구현 상태:
  "fake"     → FakeAnalysisProvider (항상 사용 가능)
  "openai"   → OpenAIAnalysisProvider (C-2.7.1; API key 필요)
  "anthropic" → ProviderNotImplementedError (미구현)

사용 예:
    provider = get_analysis_provider("fake")
    provider = get_analysis_provider("openai")   # settings.ai_openai_api_key 필요
"""
from __future__ import annotations

from app.services.ai_analysis.base import AnalysisProvider
from app.services.ai_analysis.fake import FakeAnalysisProvider

_SUPPORTED_PROVIDERS: frozenset[str] = frozenset({"fake", "openai", "anthropic"})
_IMPLEMENTED_PROVIDERS: frozenset[str] = frozenset({"fake", "openai"})


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

    if provider_name == "openai":
        from app.core.config import get_settings
        from app.services.ai_analysis.openai_provider import OpenAIAnalysisProvider
        s = get_settings()
        return OpenAIAnalysisProvider(
            api_key=s.ai_openai_api_key,
            default_model=s.ai_openai_model,
            default_timeout_seconds=s.ai_openai_timeout_seconds,
        )

    # "anthropic" — 향후 구현
    raise ProviderNotImplementedError(provider_name)
