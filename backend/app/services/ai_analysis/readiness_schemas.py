"""AI Provider readiness/preflight 응답 스키마 (C-2.7.3)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

AIProviderStatus = Literal["available", "missing_config", "not_implemented"]


class AIProviderStatusRead(BaseModel):
    provider: str
    implemented: bool
    configured: bool
    default_model: str | None
    missing_settings: list[str]
    status: AIProviderStatus
    note: str | None
