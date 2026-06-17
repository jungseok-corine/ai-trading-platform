"""AI Analysis Run API 스키마 (C-2.4).

AiAnalysisRun / AiModelResponse ORM 객체를 API 응답으로 직렬화하기 위한 Pydantic 모델.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AnalysisRunCreateRequest(BaseModel):
    prompt_type: str = "overview"
    provider: str = "fake"
    model: str | None = None


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
