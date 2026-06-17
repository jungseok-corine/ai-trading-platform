"""AI Provider readiness/preflight 서비스 (C-2.7.3).

실제 LLM 호출 없이 설정 상태와 구현 여부만 확인한다.

판단 기준:
  fake      → implemented=True, configured=True, status="available" (항상)
  openai    → configured=True iff AI_OPENAI_API_KEY 존재, 없으면 "missing_config"
  anthropic → configured=True iff AI_ANTHROPIC_API_KEY 존재, 없으면 "missing_config"
  기타 이름  → get_provider_status() returns None
"""
from __future__ import annotations

from app.core.config import get_settings
from app.services.ai_analysis.readiness_schemas import AIProviderStatusRead

# 알려진 provider 전체 목록 (표시 순서 포함)
_ALL_PROVIDERS: tuple[str, ...] = ("fake", "openai", "anthropic")
_IMPLEMENTED: frozenset[str] = frozenset({"fake", "openai", "anthropic"})


class AIProviderReadinessService:
    """provider 설정 상태를 조회한다. DB/네트워크 의존성 없음."""

    def __init__(self) -> None:
        self._s = get_settings()

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def get_provider_status(self, provider_name: str) -> AIProviderStatusRead | None:
        """provider_name의 readiness 상태를 반환한다.

        알 수 없는 이름이면 None을 반환한다.
        """
        if provider_name not in _ALL_PROVIDERS:
            return None

        if provider_name not in _IMPLEMENTED:
            return AIProviderStatusRead(
                provider=provider_name,
                implemented=False,
                configured=False,
                default_model=None,
                missing_settings=[],
                status="not_implemented",
                note=f"Provider '{provider_name}' is not yet implemented.",
            )

        return self._build_status(provider_name)

    def list_provider_statuses(self) -> list[AIProviderStatusRead]:
        """모든 알려진 provider의 readiness 상태 목록을 반환한다."""
        result: list[AIProviderStatusRead] = []
        for name in _ALL_PROVIDERS:
            status = self.get_provider_status(name)
            if status is not None:
                result.append(status)
        return result

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    def _build_status(self, provider_name: str) -> AIProviderStatusRead:
        s = self._s

        if provider_name == "fake":
            return AIProviderStatusRead(
                provider="fake",
                implemented=True,
                configured=True,
                default_model="fake-1.0",
                missing_settings=[],
                status="available",
                note="Deterministic no-op provider for testing. No API key required.",
            )

        if provider_name == "openai":
            has_key = bool(s.ai_openai_api_key)
            missing = [] if has_key else ["AI_OPENAI_API_KEY"]
            return AIProviderStatusRead(
                provider="openai",
                implemented=True,
                configured=has_key,
                default_model=s.ai_openai_model,
                missing_settings=missing,
                status="available" if has_key else "missing_config",
                note=None if has_key else "Set AI_OPENAI_API_KEY in environment to enable.",
            )

        if provider_name == "anthropic":
            has_key = bool(s.ai_anthropic_api_key)
            missing = [] if has_key else ["AI_ANTHROPIC_API_KEY"]
            return AIProviderStatusRead(
                provider="anthropic",
                implemented=True,
                configured=has_key,
                default_model=s.ai_anthropic_model,
                missing_settings=missing,
                status="available" if has_key else "missing_config",
                note=None if has_key else "Set AI_ANTHROPIC_API_KEY in environment to enable.",
            )

        return None  # pragma: no cover — _ALL_PROVIDERS 와 이 분기가 항상 동기화되어야 함
