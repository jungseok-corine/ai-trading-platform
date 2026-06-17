"""AnalysisRunService — single/dual-model analysis run (C-2.4 / C-2.5).

실행 흐름 (single):
  1. prompt_type / provider / mode 유효성 선제 검증
  2. input payload 수집 (재현/감사용)
  3. prompt 생성
  4. AiAnalysisRun row 생성 (status=RUNNING)
  5. provider.analyze(prompt) 호출
  6. AiModelResponse 저장 (role=primary_analysis)
  7. run status → SUCCEEDED / FAILED

실행 흐름 (dual):
  1~4. 동일
  5. primary provider.analyze(prompt) 호출
  6. secondary provider.analyze(prompt) 호출 (독립 실행)
  7. AiModelResponse 두 개 저장 (primary_analysis / secondary_analysis)
  8. 둘 다 성공 → SUCCEEDED; 한쪽 실패 → FAILED (양쪽 response 모두 저장)

보안:
  - 실제 OpenAI/Anthropic API 호출 없음 (FakeAnalysisProvider 기본)
  - critique / synthesis / debate 미구현
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.ai_analysis import AiAnalysisRun
from app.domain.models.enums import AnalysisRunMode, AnalysisRunStatus, AnalysisRunType, AnalysisTargetType
from app.domain.repositories.ai_analysis import AiAnalysisRunRepository, AiModelResponseRepository
from app.services.ai_analysis.base import AnalysisProvider
from app.services.ai_analysis.factory import (
    ProviderNotImplementedError,
    UnknownProviderError,
    get_analysis_provider,
)
from app.services.ai_analysis.schemas import AnalysisProviderError, AnalysisProviderResult
from app.services.strategy_analysis_input_service import StrategyAnalysisInputService
from app.services.strategy_analysis_prompt_service import (
    SUPPORTED_PROMPT_TYPES,
    StrategyAnalysisPromptService,
    UnsupportedPromptTypeError,
)

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

_ROLE_PRIMARY = "primary_analysis"
_ROLE_SECONDARY = "secondary_analysis"


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
        mode: str = "single",
        secondary_provider_name: str | None = None,
        secondary_model: str | None = None,
    ) -> AiAnalysisRun | None:
        """분석을 실행하고 결과를 저장한다 (single / dual mode).

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

        run_mode = AnalysisRunMode(mode)
        primary = get_analysis_provider(provider_name)   # raises Unknown / NotImplemented
        used_model = model or primary.default_model()

        secondary: AnalysisProvider | None = None
        used_secondary_model: str | None = None
        if run_mode is AnalysisRunMode.DUAL:
            assert secondary_provider_name is not None  # enforced by schema validator
            secondary = get_analysis_provider(secondary_provider_name)
            used_secondary_model = secondary_model or secondary.default_model()

        # 2. input payload 수집 (재현/감사용 스냅샷)
        input_svc = StrategyAnalysisInputService(self._session)
        input_data = await input_svc.get_analysis_input(strategy_id, version_id)
        if input_data is None:
            return None   # strategy/version 없음

        payload_dict = input_data.model_dump(mode="json")
        # analysis_context.generated_at은 호출마다 달라지므로 hash 대상에서 제외.
        payload_for_hash = {k: v for k, v in payload_dict.items() if k != "analysis_context"}
        input_canonical = json.dumps(payload_for_hash, sort_keys=True, ensure_ascii=True, default=str)
        input_hash = hashlib.sha256((input_canonical + "|" + prompt_type).encode()).hexdigest()

        # 3. prompt 생성
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
            mode=run_mode,
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

        if run_mode is AnalysisRunMode.SINGLE:
            return await self._execute_single(run, primary, used_model, prompt_result.prompt)
        else:
            return await self._execute_dual(
                run,
                primary, used_model,
                secondary, used_secondary_model,  # type: ignore[arg-type]
                secondary_provider_name,           # type: ignore[arg-type]
                prompt_result.prompt,
            )

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

    # ------------------------------------------------------------------
    # private helpers
    # ------------------------------------------------------------------

    async def _execute_single(
        self,
        run: AiAnalysisRun,
        provider: AnalysisProvider,
        used_model: str,
        prompt: str,
    ) -> AiAnalysisRun:
        try:
            result = await provider.analyze(prompt, model=used_model)
            await self._save_response(run.id, result, _ROLE_PRIMARY)
            run = await self._run_repo.update(
                run,
                status=AnalysisRunStatus.SUCCEEDED,
                completed_at=datetime.now(KST),
            )
        except AnalysisProviderError as exc:
            logger.warning(
                "AI provider error in run %s: %s (retryable=%s)", run.id, exc.message, exc.retryable
            )
            await self._save_error_response(run.id, provider.provider_name(), used_model, _ROLE_PRIMARY, exc)
            run = await self._run_repo.update(
                run,
                status=AnalysisRunStatus.FAILED,
                error_message=exc.message,
                completed_at=datetime.now(KST),
            )
        return await self._run_repo.get_with_responses(run.id)

    async def _execute_dual(
        self,
        run: AiAnalysisRun,
        primary: AnalysisProvider,
        primary_model: str,
        secondary: AnalysisProvider,
        secondary_model: str,
        secondary_provider_name: str,
        prompt: str,
    ) -> AiAnalysisRun:
        errors: list[str] = []

        # primary
        try:
            primary_result = await primary.analyze(prompt, model=primary_model)
            await self._save_response(run.id, primary_result, _ROLE_PRIMARY)
        except AnalysisProviderError as exc:
            logger.warning(
                "Primary provider error in dual run %s: %s", run.id, exc.message
            )
            await self._save_error_response(run.id, primary.provider_name(), primary_model, _ROLE_PRIMARY, exc)
            errors.append(f"primary({primary.provider_name()}): {exc.message}")

        # secondary (독립 실행 — primary 결과와 무관)
        try:
            secondary_result = await secondary.analyze(prompt, model=secondary_model)
            await self._save_response(run.id, secondary_result, _ROLE_SECONDARY)
        except AnalysisProviderError as exc:
            logger.warning(
                "Secondary provider error in dual run %s: %s", run.id, exc.message
            )
            await self._save_error_response(
                run.id, secondary.provider_name(), secondary_model, _ROLE_SECONDARY, exc
            )
            errors.append(f"secondary({secondary.provider_name()}): {exc.message}")

        if errors:
            run = await self._run_repo.update(
                run,
                status=AnalysisRunStatus.FAILED,
                error_message="; ".join(errors),
                completed_at=datetime.now(KST),
            )
        else:
            run = await self._run_repo.update(
                run,
                status=AnalysisRunStatus.SUCCEEDED,
                completed_at=datetime.now(KST),
            )

        return await self._run_repo.get_with_responses(run.id)

    async def _save_response(
        self, run_id: int, result: AnalysisProviderResult, role: str
    ) -> None:
        await self._response_repo.create(
            run_id=run_id,
            provider=result.provider,
            model=result.model,
            role=role,
            content=result.content,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            latency_ms=result.latency_ms,
            finish_reason=result.finish_reason,
            raw=result.raw,
        )

    async def _save_error_response(
        self,
        run_id: int,
        provider_name: str,
        used_model: str,
        role: str,
        exc: AnalysisProviderError,
    ) -> None:
        await self._response_repo.create(
            run_id=run_id,
            provider=provider_name,
            model=used_model,
            role=role,
            content=None,
            finish_reason="error",
            error_message=exc.message,
        )
