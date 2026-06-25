"""Paper Signal Session AI 분석 run 서비스 (V1: analysis-report only).

PaperSignalAnalysisInput → bounded prompt → AI provider 호출 → AiAnalysisRun + AiModelResponse 저장.

**하드 경계 (코드 레벨로 보장):**
- AiAnalysisRun / AiModelResponse만 만든다. 다른 어떤 도메인 객체도 만들지 않는다.
- CandidateStrategyProposal/ScannerRuleProposal/StrategyVersion/Experiment/SignalLog/Trade/Order/
  StrategyAssignmentLog 생성 없음. 세션/전략/실험 상태 변경 없음. 스케줄러/잡 미점화.
- TradeService/OrderService/StrategyRunnerService/broker 미사용.
- 기본 provider는 fake(오프라인). 실 provider는 명시 요청 + API 키가 있을 때만 동작(factory가 가드).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.ai_analysis import AiAnalysisRun
from app.domain.models.enums import (
    AnalysisRunMode,
    AnalysisRunStatus,
    AnalysisRunType,
    AnalysisTargetType,
)
from app.domain.repositories.ai_analysis import (
    AiAnalysisRunRepository,
    AiModelResponseRepository,
)
from app.domain.repositories.paper_signal_session import PaperSignalSessionRepository
from app.services.ai_analysis.factory import get_analysis_provider
from app.services.ai_analysis.schemas import AnalysisProviderError
from app.services.paper_signal_analysis_input_service import (
    InvalidHorizonError,
    PaperSignalAnalysisInputService,
    SessionNotFoundError,
)
from app.services.paper_signal_analysis_prompt_service import (
    PaperSignalAnalysisPromptService,
)

_PROMPT_TYPE = "paper_signal_session"
_ROLE = "primary_analysis"


class ConfirmationRequiredError(Exception):
    """confirmed=true / confirmed_by 없이 분석을 요청할 때."""


class InvalidModeError(Exception):
    """V1은 single 모드만 지원한다."""


class PaperSignalAnalysisRunService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._session_repo = PaperSignalSessionRepository(session)
        self._input_service = PaperSignalAnalysisInputService(session)
        self._prompt_service = PaperSignalAnalysisPromptService()
        self._run_repo = AiAnalysisRunRepository(session)
        self._response_repo = AiModelResponseRepository(session)

    async def create_run(
        self,
        session_id: int,
        horizon_minutes: int = 30,
        provider: str = "fake",
        mode: str = "single",
        confirmed: bool = False,
        confirmed_by: str | None = None,
        model: str | None = None,
    ) -> AiAnalysisRun:
        if not confirmed:
            raise ConfirmationRequiredError("confirmed must be true")
        if not confirmed_by:
            raise ConfirmationRequiredError("confirmed_by is required")
        if mode != "single":
            raise InvalidModeError("V1 supports mode='single' only")

        sess = await self._session_repo.get(session_id)
        if sess is None:
            raise SessionNotFoundError(session_id)

        # 분석 입력(읽기 전용). horizon 검증(InvalidHorizonError) 포함.
        analysis_input = (
            await self._input_service.build_input(session_id, horizon_minutes=horizon_minutes)
        ).to_dict()

        prompt_result = self._prompt_service.build(analysis_input)

        # input_hash: generated_at는 호출마다 달라지므로 제외.
        payload_for_hash = {k: v for k, v in analysis_input.items() if k != "generated_at"}
        input_canonical = json.dumps(payload_for_hash, sort_keys=True, ensure_ascii=True, default=str)
        input_hash = hashlib.sha256((input_canonical + "|" + _PROMPT_TYPE).encode()).hexdigest()
        prompt_hash = hashlib.sha256(prompt_result.prompt.encode()).hexdigest()

        prov = get_analysis_provider(provider)
        used_model = model or prov.default_model()

        now = datetime.now(timezone.utc)
        run = await self._run_repo.create(
            analysis_type=AnalysisRunType.PAPER_SIGNAL_SESSION_ANALYSIS,
            target_type=AnalysisTargetType.PAPER_SIGNAL_SESSION,
            target_id=sess.id,
            strategy_id=None,
            strategy_version_id=sess.strategy_version_id,  # 추적용(있으면)
            mode=AnalysisRunMode.SINGLE,
            prompt_type=_PROMPT_TYPE,
            provider=provider,
            model=used_model,
            status=AnalysisRunStatus.RUNNING,
            input_payload=analysis_input,
            input_hash=input_hash,
            prompt=prompt_result.prompt,
            prompt_hash=prompt_hash,
            prompt_length=prompt_result.prompt_length,
            truncated=prompt_result.truncated,
            warnings=prompt_result.warnings or None,
            started_at=now,
        )

        try:
            result = await prov.analyze(prompt_result.prompt, model=used_model)
            await self._response_repo.create(
                run_id=run.id,
                provider=result.provider,
                model=result.model,
                role=_ROLE,
                content=result.content,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
                latency_ms=result.latency_ms,
                finish_reason=result.finish_reason,
                raw=result.raw,
            )
            run = await self._run_repo.update(
                run, status=AnalysisRunStatus.SUCCEEDED, completed_at=datetime.now(timezone.utc)
            )
        except AnalysisProviderError as exc:
            await self._response_repo.create(
                run_id=run.id,
                provider=provider,
                model=used_model,
                role=_ROLE,
                content=None,
                finish_reason="error",
                error_message=exc.message,
            )
            run = await self._run_repo.update(
                run,
                status=AnalysisRunStatus.FAILED,
                error_message=exc.message,
                completed_at=datetime.now(timezone.utc),
            )
        await self._session.commit()
        return await self._run_repo.get_with_responses(run.id)

    async def list_runs_for_session(
        self, session_id: int, limit: int = 20
    ) -> list[AiAnalysisRun]:
        return await self._run_repo.list_by_target(
            AnalysisTargetType.PAPER_SIGNAL_SESSION, session_id, limit=limit
        )


__all__ = [
    "PaperSignalAnalysisRunService",
    "ConfirmationRequiredError",
    "InvalidModeError",
    "SessionNotFoundError",
    "InvalidHorizonError",
]
