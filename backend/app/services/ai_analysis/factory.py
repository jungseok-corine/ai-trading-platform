"""AI Analysis Provider factory.

get_analysis_provider()로 provider 이름을 받아 구현체를 반환한다.

구현 상태:
  "fake"      → FakeAnalysisProvider (항상 사용 가능, 네트워크 없음)
  "openai"    → OpenAIAnalysisProvider (C-2.7.1; AI_OPENAI_API_KEY 필요)
  "anthropic" → AnthropicAnalysisProvider (C-2.7.2; AI_ANTHROPIC_API_KEY 필요)

사용 예:
    provider = get_analysis_provider("fake")
    provider = get_analysis_provider("openai")      # settings.ai_openai_api_key 필요
    provider = get_analysis_provider("anthropic")   # settings.ai_anthropic_api_key 필요
"""
from __future__ import annotations

from app.services.ai_analysis.base import AnalysisProvider
from app.services.ai_analysis.fake import FakeAnalysisProvider

_SUPPORTED_PROVIDERS: frozenset[str] = frozenset({"fake", "openai", "anthropic"})
_IMPLEMENTED_PROVIDERS: frozenset[str] = frozenset({"fake", "openai", "anthropic"})


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
        ProviderNotImplementedError: 알려진 provider이지만 아직 구현되지 않음 (현재 해당 없음)
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
            max_output_tokens=s.ai_openai_max_output_tokens,
        )

    if provider_name == "anthropic":
        from app.core.config import get_settings
        from app.services.ai_analysis.anthropic_provider import AnthropicAnalysisProvider
        s = get_settings()
        return AnthropicAnalysisProvider(
            api_key=s.ai_anthropic_api_key,
            default_model=s.ai_anthropic_model,
            default_timeout_seconds=s.ai_anthropic_timeout_seconds,
            max_tokens=s.ai_anthropic_max_tokens,
        )

    # 이 시점에 도달하는 provider는 현재 없음 (향후 확장 대비)
    raise ProviderNotImplementedError(provider_name)  # pragma: no cover
