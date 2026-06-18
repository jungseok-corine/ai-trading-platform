from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.ai_analysis.factory import ProviderNotImplementedError, UnknownProviderError
from app.services.ai_analysis.run_schemas import AnalysisRunCreateRequest, AnalysisRunRead
from app.services.ai_analysis.run_service import AnalysisRunService
from app.services.strategy_analysis_input_service import StrategyAnalysisInputService
from app.services.strategy_analysis_prompt_service import (
    SUPPORTED_PROMPT_TYPES,
    StrategyAnalysisPromptService,
    UnsupportedPromptTypeError,
)
from app.services.strategy_performance_service import StrategyPerformanceService
from app.services.strategy_service import (
    StrategyNotFoundError,
    StrategyService,
    StrategyVersionNotFoundError,
)
from app.trading.strategy.schemas import (
    STRATEGY_TYPES_METADATA,
    StrategyAnalysisInputRead,
    StrategyAnalysisPromptRead,
    StrategyCreateRequest,
    StrategyRead,
    StrategyTypeMeta,
    StrategyVersionCreateRequest,
    StrategyVersionPerformanceRead,
    StrategyVersionRead,
    StrategyVersionUpdateRequest,
)

router = APIRouter(prefix="/strategies", tags=["strategies"])


def get_strategy_service(session: AsyncSession = Depends(get_db)) -> StrategyService:
    return StrategyService(session)


def get_performance_service(session: AsyncSession = Depends(get_db)) -> StrategyPerformanceService:
    return StrategyPerformanceService(session)


def get_analysis_input_service(
    session: AsyncSession = Depends(get_db),
) -> StrategyAnalysisInputService:
    return StrategyAnalysisInputService(session)


def get_analysis_prompt_service(
    session: AsyncSession = Depends(get_db),
) -> StrategyAnalysisPromptService:
    return StrategyAnalysisPromptService(session)


def get_analysis_run_service(
    session: AsyncSession = Depends(get_db),
) -> AnalysisRunService:
    return AnalysisRunService(session)


@router.get("/strategy-types", response_model=list[StrategyTypeMeta])
async def list_strategy_types() -> list[StrategyTypeMeta]:
    """등록된 전략 타입과 파라미터 메타데이터를 반환한다.

    프론트엔드 폼 동적 생성에 사용된다.
    """
    return STRATEGY_TYPES_METADATA


@router.get("", response_model=list[StrategyRead])
async def list_strategies(service: StrategyService = Depends(get_strategy_service)) -> list[StrategyRead]:
    pairs = await service.list_strategies()
    return [
        StrategyRead(
            id=strategy.id,
            name=strategy.name,
            description=strategy.description,
            created_at=strategy.created_at,
            version_count=count,
        )
        for strategy, count in pairs
    ]


@router.post("", response_model=StrategyRead)
async def create_strategy(
    payload: StrategyCreateRequest,
    service: StrategyService = Depends(get_strategy_service),
) -> StrategyRead:
    strategy = await service.create_strategy(payload.name, payload.description)
    return StrategyRead(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        created_at=strategy.created_at,
        version_count=0,
    )


@router.get("/{strategy_id}/versions", response_model=list[StrategyVersionRead])
async def list_strategy_versions(
    strategy_id: int,
    service: StrategyService = Depends(get_strategy_service),
) -> list[StrategyVersionRead]:
    try:
        return await service.list_versions(strategy_id)
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail="strategy not found") from e


@router.post("/{strategy_id}/versions", response_model=StrategyVersionRead)
async def create_strategy_version(
    strategy_id: int,
    payload: StrategyVersionCreateRequest,
    service: StrategyService = Depends(get_strategy_service),
) -> StrategyVersionRead:
    try:
        return await service.create_version(
            strategy_id,
            parameters=payload.parameters.model_dump(),
            change_description=payload.change_description,
            status=payload.status,
        )
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail="strategy not found") from e


@router.get(
    "/{strategy_id}/versions/{version_id}/performance",
    response_model=StrategyVersionPerformanceRead,
)
async def get_version_performance(
    strategy_id: int,
    version_id: int,
    service: StrategyPerformanceService = Depends(get_performance_service),
) -> StrategyVersionPerformanceRead:
    """strategy_version의 신호 기반 성과와 실제 체결 성과를 반환한다.

    신호가 없으면 빈 집계(zeros)를 반환한다.
    strategy_id/version_id 조합이 없으면 404.
    """
    performance = await service.get_version_performance(strategy_id, version_id)
    if performance is None:
        raise HTTPException(status_code=404, detail="strategy version not found")
    return performance


@router.get(
    "/{strategy_id}/versions/{version_id}/analysis-input",
    response_model=StrategyAnalysisInputRead,
)
async def get_analysis_input(
    strategy_id: int,
    version_id: int,
    service: StrategyAnalysisInputService = Depends(get_analysis_input_service),
) -> StrategyAnalysisInputRead:
    """LLM에 바로 넘길 수 있는 strategy_version 분석 입력 payload를 반환한다.

    strategy_id/version_id 조합이 없으면 404.
    데이터(신호, market_data, 실제 거래)가 없어도 payload는 항상 생성된다.
    """
    result = await service.get_analysis_input(strategy_id, version_id)
    if result is None:
        raise HTTPException(status_code=404, detail="strategy version not found")
    return result


@router.get(
    "/{strategy_id}/versions/{version_id}/analysis-prompt",
    response_model=StrategyAnalysisPromptRead,
)
async def get_analysis_prompt(
    strategy_id: int,
    version_id: int,
    prompt_type: str = Query(default="overview"),
    service: StrategyAnalysisPromptService = Depends(get_analysis_prompt_service),
) -> StrategyAnalysisPromptRead:
    """LLM 분석용 prompt를 생성해 반환한다.

    prompt_type: overview (기본) | risk | improvement
    지원하지 않는 prompt_type은 400 반환.
    strategy_id/version_id 조합을 찾을 수 없으면 404 반환.
    LLM API 호출 없음 — prompt text preview만 제공한다.
    """
    try:
        result = await service.get_prompt(strategy_id, version_id, prompt_type)
    except UnsupportedPromptTypeError:
        supported = ", ".join(sorted(SUPPORTED_PROMPT_TYPES))
        raise HTTPException(
            status_code=400,
            detail=f"unsupported prompt_type: '{prompt_type}'. supported: {supported}",
        )
    if result is None:
        raise HTTPException(status_code=404, detail="strategy version not found")
    return result


@router.post(
    "/{strategy_id}/versions/{version_id}/analysis-runs",
    response_model=AnalysisRunRead,
    status_code=201,
)
async def create_analysis_run(
    strategy_id: int,
    version_id: int,
    payload: AnalysisRunCreateRequest,
    service: AnalysisRunService = Depends(get_analysis_run_service),
) -> AnalysisRunRead:
    """strategy_version에 대해 single-model 분석을 실행하고 결과를 저장한다.

    FakeAnalysisProvider (기본) 또는 향후 openai/anthropic provider 사용.
    실제 LLM API 호출 여부는 provider 설정에 따라 결정된다.
    """
    try:
        run = await service.create_run(
            strategy_id=strategy_id,
            version_id=version_id,
            prompt_type=payload.prompt_type,
            provider_name=payload.provider,
            model=payload.model,
            mode=payload.mode,
            secondary_provider_name=payload.secondary_provider,
            secondary_model=payload.secondary_model,
            enable_critique=payload.enable_critique,
            enable_synthesis=payload.enable_synthesis,
        )
    except UnsupportedPromptTypeError:
        supported = ", ".join(sorted(SUPPORTED_PROMPT_TYPES))
        raise HTTPException(
            status_code=400,
            detail=f"unsupported prompt_type: '{payload.prompt_type}'. supported: {supported}",
        )
    except (UnknownProviderError, ProviderNotImplementedError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if run is None:
        raise HTTPException(status_code=404, detail="strategy version not found")
    return AnalysisRunRead.model_validate(run)


@router.get(
    "/{strategy_id}/versions/{version_id}/analysis-runs",
    response_model=list[AnalysisRunRead],
)
async def list_analysis_runs(
    strategy_id: int,
    version_id: int,
    service: AnalysisRunService = Depends(get_analysis_run_service),
) -> list[AnalysisRunRead]:
    """strategy_version에 대한 분석 run 목록을 최신 순으로 반환한다."""
    runs = await service.list_runs_for_version(strategy_id, version_id)
    return [AnalysisRunRead.model_validate(r) for r in runs]


@router.patch("/{strategy_id}/versions/{version_id}", response_model=StrategyVersionRead)
async def update_strategy_version(
    strategy_id: int,
    version_id: int,
    payload: StrategyVersionUpdateRequest,
    service: StrategyService = Depends(get_strategy_service),
) -> StrategyVersionRead:
    fields = payload.model_dump(exclude_unset=True, exclude={"parameters"})
    if payload.parameters is not None:
        fields["parameters"] = payload.parameters.model_dump()
    try:
        return await service.update_version(strategy_id, version_id, **fields)
    except (StrategyNotFoundError, StrategyVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail="strategy version not found") from e
