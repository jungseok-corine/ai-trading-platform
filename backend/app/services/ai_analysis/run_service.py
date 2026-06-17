"""AnalysisRunService — single-model analysis run (C-2.4).

실행 흐름:
  1. prompt_type / provider 유효성 선제 검증
  2. StrategyAnalysisPromptService로 prompt 생성 (strategy/version 존재 확인 겸용)
  3. AiAnalysisRun row 생성 (status=RUNNING)
  4. provider.analyze(prompt) 호출
  5. AiModelResponse 저장
  6. run status → SUCCEEDED
  예외: AnalysisProviderError → run status → FAILED, error_message 저장

보안:
  - 실제 OpenAI/Anthropic API 호출 없음 (FakeAnalysisProvider 기본)
  - DB 스키마 변경 없음 (migration은 별도 파일)
  - 전략 자동 수정/활성화 없음
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.ai_analysis import AiAnalysisRun
from app.domain.models.enums import AnalysisRunStatus, AnalysisRunType, AnalysisTargetType
from app.domain.repositories.ai_analysis import AiAnalysisRunRepository, AiModelResponseRepository
from app.services.ai_analysis.factory import (
    ProviderNotImplementedError,
    UnknownProviderError,
    get_analysis_provider,
)
from app.services.ai_analysis.schemas import AnalysisProviderError
from app.services.strategy_analysis_input_service import StrategyAnalysisInputService
from app.services.strategy_analysis_prompt_service import (
    SUPPORTED_PROMPT_TYPES,
    StrategyAnalysisPromptService,
    UnsupportedPromptTypeError,
)

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

_ROLE_PRIMARY = "primary_analysis"


class AnalysisRunService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._run_repo = AiAnalysisRunRepository(session)
        self._response_repo = AiModelResponseRepository(session)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    async def create_run(
        self,
        strategy_id: int,
        version_id: int,
        prompt_type: str,
        provider_name: str,
        model: str | None = None,
    ) -> AiAnalysisRun | None:
        """단일 모델 분석을 실행하고 결과를 저장한다.

        Returns:
            AiAnalysisRun (responses 포함) on success or failure.
            None if strategy_id/version_id combination does not exist.

        Raises:
            UnsupportedPromptTypeError: 지원하지 않는 prompt_type.
            UnknownProviderError: 알 수 없는 provider 이름.
            ProviderNotImplementedError: 아직 구현되지 않은 provider.
        """
        # 1. 선제 유효성 검증 (DB row 생성 전)
        if prompt_type not in SUPPORTED_PROMPT_TYPES:
            raise UnsupportedPromptTypeError(prompt_type)

        provider = get_analysis_provider(provider_name)   # raises Unknown / NotImplemented
        used_model = model or provider.default_model()

        # 2. input payload 수집 (재현/감사용 스냅샷)
        input_svc = StrategyAnalysisInputService(self._session)
        input_data = await input_svc.get_analysis_input(strategy_id, version_id)
        if input_data is None:
            return None   # strategy/version 없음

        payload_dict = input_data.model_dump(mode="json")
        # analysis_context는 payload 생성 시각(generated_at)만 담고 있어
        # 호출마다 달라진다. 동일 input + prompt_type + provider + model →
        # 동일 input_hash를 보장하기 위해 hash 대상에서 제외한다.
        payload_for_hash = {k: v for k, v in payload_dict.items() if k != "analysis_context"}
        input_canonical = json.dumps(payload_for_hash, sort_keys=True, ensure_ascii=True, default=str)
        input_hash_src = input_canonical + "|" + prompt_type + "|" + provider_name + "|" + used_model
        input_hash = hashlib.sha256(input_hash_src.encode()).hexdigest()

        # 3. prompt 생성 (strategy/version 존재 확인 겸용 — input_svc와 별도 DB reads 허용)
        prompt_svc = StrategyAnalysisPromptService(self._session)
        prompt_result = await prompt_svc.get_prompt(strategy_id, version_id, prompt_type)
        if prompt_result is None:
            return None   # defensive

        prompt_hash = hashlib.sha256(prompt_result.prompt.encode()).hexdigest()

        # 4. run row 생성
        now = datetime.now(KST)
        run = await self._run_repo.create(
            analysis_type=AnalysisRunType.STRATEGY_PERFORMANCE,
            target_type=AnalysisTargetType.STRATEGY_VERSION,
            target_id=version_id,
            strategy_id=strategy_id,
            strategy_version_id=version_id,
            prompt_type=prompt_type,
            provider=provider_name,
            model=used_model,
            status=AnalysisRunStatus.RUNNING,
            input_payload=payload_dict,
            input_hash=input_hash,
            prompt=prompt_result.prompt,
            prompt_hash=prompt_hash,
            prompt_length=prompt_result.prompt_length,
            truncated=prompt_result.truncated,
            warnings=prompt_result.warnings if prompt_result.warnings else None,
            started_at=now,
        )

        # 5. provider 호출
        try:
            result = await provider.analyze(prompt_result.prompt, model=used_model)

            # 6. response 저장
            await self._response_repo.create(
                run_id=run.id,
                provider=result.provider,
                model=result.model,
                role=_ROLE_PRIMARY,
                content=result.content,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
                latency_ms=result.latency_ms,
                finish_reason=result.finish_reason,
                raw=result.raw,
            )

            # 7. run status → SUCCEEDED
            run = await self._run_repo.update(
                run,
                status=AnalysisRunStatus.SUCCEEDED,
                completed_at=datetime.now(KST),
            )

        except AnalysisProviderError as exc:
            logger.warning(
                "AI provider error during analysis run %s: %s (retryable=%s)",
                run.id, exc.message, exc.retryable,
            )
            # response row에 에러 기록
            await self._response_repo.create(
                run_id=run.id,
                provider=provider_name,
                model=used_model,
                role=_ROLE_PRIMARY,
                content=None,
                finish_reason="error",
                error_message=exc.message,
            )
            run = await self._run_repo.update(
                run,
                status=AnalysisRunStatus.FAILED,
                error_message=exc.message,
                completed_at=datetime.now(KST),
            )

        # 7. responses 포함해서 반환
        return await self._run_repo.get_with_responses(run.id)

    async def get_run(self, run_id: int) -> AiAnalysisRun | None:
        """run_id로 단일 run을 조회한다 (responses 포함)."""
        return await self._run_repo.get_with_responses(run_id)

    async def list_runs_for_version(
        self,
        strategy_id: int,
        version_id: int,
        limit: int = 20,
    ) -> list[AiAnalysisRun]:
        """strategy_version에 대한 run 목록을 최신 순으로 반환한다."""
        return await self._run_repo.list_by_strategy_version(strategy_id, version_id, limit)
