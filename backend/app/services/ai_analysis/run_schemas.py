"""AI Analysis Run API 스키마 (C-2.4 / C-2.5 / C-2.6).

AiAnalysisRun / AiModelResponse ORM 객체를 API 응답으로 직렬화하기 위한 Pydantic 모델.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class AnalysisRunCreateRequest(BaseModel):
    prompt_type: str = "overview"
    mode: Literal["single", "dual"] = "single"
    provider: str = "fake"
    model: str | None = None
    secondary_provider: str | None = None
    secondary_model: str | None = None
    enable_critique: bool = False
    enable_synthesis: bool = False

    @model_validator(mode="after")
    def _validate_options(self) -> "AnalysisRunCreateRequest":
        if self.mode == "dual" and not self.secondary_provider:
            raise ValueError("secondary_provider is required when mode='dual'")
        if self.mode != "dual" and (self.enable_critique or self.enable_synthesis):
            raise ValueError(
                "enable_critique and enable_synthesis require mode='dual'"
            )
        return self


class AiModelResponseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    provider: str
    model: str
    role: str
    content: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_ms: int | None
    finish_reason: str | None
    error_message: str | None
    created_at: datetime


class AnalysisRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_type: str
    target_type: str
    target_id: int
    strategy_id: int | None
    strategy_version_id: int | None
    mode: str
    prompt_type: str
    provider: str
    model: str
    status: str
    input_hash: str | None
    prompt_hash: str | None
    prompt_length: int | None
    truncated: bool
    warnings: list[str] | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    responses: list[AiModelResponseRead]
