"""GET /api/v1/ai-analysis/providers — AI provider readiness API (C-2.7.3)."""
from fastapi import APIRouter, HTTPException

from app.services.ai_analysis.readiness_schemas import AIProviderStatusRead
from app.services.ai_analysis.readiness_service import AIProviderReadinessService

router = APIRouter(prefix="/ai-analysis/providers", tags=["ai-analysis"])


def _svc() -> AIProviderReadinessService:
    return AIProviderReadinessService()


@router.get("", response_model=list[AIProviderStatusRead])
async def list_ai_providers() -> list[AIProviderStatusRead]:
    """모든 AI provider의 설정 상태를 반환한다. 실제 LLM 호출 없음."""
    return _svc().list_provider_statuses()


@router.get("/{provider_name}", response_model=AIProviderStatusRead)
async def get_ai_provider(provider_name: str) -> AIProviderStatusRead:
    """특정 AI provider의 설정 상태를 반환한다.

    알 수 없는 provider_name이면 404를 반환한다.
    """
    status = _svc().get_provider_status(provider_name)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown AI provider: '{provider_name}'. Known providers: fake, openai, anthropic.",
        )
    return status
