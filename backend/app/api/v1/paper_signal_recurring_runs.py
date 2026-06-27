"""Pair-Scoped Recurring Signal Run Plan API (M2.14A/B-1/B-2).

계획을 **생성·조회·중지·활성화**하고, 선택한 active 계획을 **1회 tick**한다(M2.14B-2).
tick은 디스패처/스케줄러가 아니다 — 사람이 한 계획을 고르고 confirm한 한 번만 실행한다:
선택한 두 세션만 각각 1회 평가(최대 2 SignalLog) · 주문/거래 없음 · 전체 active 스캔/잡 활성 없음.
D-24/D-25/D-26 참조.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client, get_overseas_client
from app.db.session import get_db
from app.services.market_data_service import MarketDataService
from app.services.paper_signal_pair_run_once_service import (
    BaselineMismatchError,
    NotChallengerSessionError,
    SymbolMismatchError,
)
from app.services.paper_signal_recurring_run_service import (
    DuplicateRecurringPlanError,
    PaperSignalRecurringRunService,
    RecurringBaselineNotFoundError,
    RecurringChallengerNotFoundError,
    RecurringConfirmationRequiredError,
    RecurringInvalidIntervalError,
    RecurringInvalidMaxRunsError,
    RecurringPlanExhaustedError,
    RecurringPlanNotActivatableError,
    RecurringPlanNotFoundError,
    RecurringPlanNotStoppableError,
    RecurringPlanNotTickableError,
)
from app.services.paper_signal_run_once_service import (
    MissingSymbolError,
    MissingVersionError,
    RealTradingEnabledError,
    RunnerEnabledError,
    SessionNotActiveError,
    UnsupportedStrategyTypeError,
    VersionAutoTradeError,
    VersionNotDraftError,
)
from app.services.signal_service import SignalService
from app.trading.broker.base import BrokerClient

router = APIRouter(tags=["paper-signal-recurring-runs"])


def get_recurring_run_service(
    session: AsyncSession = Depends(get_db),
) -> PaperSignalRecurringRunService:
    # 실행 경로 없음 — broker/SignalService를 주입하지 않는다(계획 관리 전용).
    return PaperSignalRecurringRunService(session)


def get_recurring_run_tick_service(
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
    overseas=Depends(get_overseas_client),
) -> PaperSignalRecurringRunService:
    # tick 전용 — signal-only SignalService(시세 조회 전용). TradeService/주문 클라이언트 미구성.
    signal_service = SignalService(
        session, MarketDataService(broker, session, overseas_client=overseas)
    )
    return PaperSignalRecurringRunService(session, signal_service=signal_service)


class CreateRecurringRunRequest(BaseModel):
    baseline_session_id: int
    challenger_session_id: int
    interval_seconds: int
    max_runs: int
    confirmed: bool = False
    confirmed_by: str | None = None
    note: str | None = None


class StopRecurringRunRequest(BaseModel):
    confirmed: bool = False
    confirmed_by: str | None = None


class ActivateRecurringRunRequest(BaseModel):
    confirmed: bool = False
    confirmed_by: str | None = None


class TickRecurringRunRequest(BaseModel):
    confirmed: bool = False
    confirmed_by: str | None = None


class RecurringRunResponse(BaseModel):
    id: int
    status: str  # prepared | active | stopped | completed | (미래: failed)
    scope_type: str
    baseline_session_id: int
    challenger_session_id: int
    interval_seconds: int
    max_runs: int
    completed_runs: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_by: str
    stopped_by: str | None
    stopped_at: datetime | None
    note: str | None
    last_error: str | None
    orders_created: int  # 항상 0
    trades_created: int  # 항상 0
    warnings: list[str]


class RecurringTickSide(BaseModel):
    session_id: int
    signal_created: bool
    signal_id: int | None
    reason: str | None


class RecurringTickResponse(RecurringRunResponse):
    baseline: RecurringTickSide
    challenger: RecurringTickSide


# validate_session/check_global_gates(M2.8) + 페어 관계(M2.10)에서 오는 자격 실패는 모두 422.
_VALIDATION_ERRORS = (
    NotChallengerSessionError,
    BaselineMismatchError,
    SymbolMismatchError,
    SessionNotActiveError,
    MissingVersionError,
    VersionNotDraftError,
    VersionAutoTradeError,
    UnsupportedStrategyTypeError,
    MissingSymbolError,
    RealTradingEnabledError,
    RunnerEnabledError,
    RecurringInvalidIntervalError,
    RecurringInvalidMaxRunsError,
)


@router.post(
    "/paper-signal-recurring-runs",
    response_model=RecurringRunResponse,
    status_code=201,
)
async def create_recurring_run(
    payload: CreateRecurringRunRequest,
    service: PaperSignalRecurringRunService = Depends(get_recurring_run_service),
) -> RecurringRunResponse:
    """pair-scoped 반복 신호 *계획*을 prepared 상태로 만든다(실행 안 함).

    주문/거래/SignalLog 없음 · 스케줄러/잡 미활성 · 디스패처 없음. 관계/세션/버전 자격 실패는 422,
    같은 페어 비종료 계획 중복은 409.
    """
    try:
        result = await service.create_prepared_pair_plan(
            baseline_session_id=payload.baseline_session_id,
            challenger_session_id=payload.challenger_session_id,
            interval_seconds=payload.interval_seconds,
            max_runs=payload.max_runs,
            confirmed=payload.confirmed,
            confirmed_by=payload.confirmed_by,
            note=payload.note,
        )
    except RecurringConfirmationRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RecurringBaselineNotFoundError as e:
        raise HTTPException(status_code=404, detail="baseline session not found") from e
    except RecurringChallengerNotFoundError as e:
        raise HTTPException(status_code=404, detail="challenger session not found") from e
    except DuplicateRecurringPlanError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except _VALIDATION_ERRORS as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return RecurringRunResponse(**result)


@router.get(
    "/paper-signal-recurring-runs",
    response_model=list[RecurringRunResponse],
)
async def list_recurring_runs(
    status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: PaperSignalRecurringRunService = Depends(get_recurring_run_service),
) -> list[RecurringRunResponse]:
    plans = await service.list_plans(status=status, limit=limit, offset=offset)
    return [RecurringRunResponse(**p) for p in plans]


@router.get(
    "/paper-signal-recurring-runs/{plan_id}",
    response_model=RecurringRunResponse,
)
async def get_recurring_run(
    plan_id: int,
    service: PaperSignalRecurringRunService = Depends(get_recurring_run_service),
) -> RecurringRunResponse:
    try:
        result = await service.get_plan(plan_id)
    except RecurringPlanNotFoundError as e:
        raise HTTPException(status_code=404, detail="recurring run plan not found") from e
    return RecurringRunResponse(**result)


@router.post(
    "/paper-signal-recurring-runs/{plan_id}/stop",
    response_model=RecurringRunResponse,
)
async def stop_recurring_run(
    plan_id: int,
    payload: StopRecurringRunRequest,
    service: PaperSignalRecurringRunService = Depends(get_recurring_run_service),
) -> RecurringRunResponse:
    """prepared/active 계획을 stopped로 바꾼다. 세션/버전/제안 불변 · SignalLog/주문/거래 없음."""
    try:
        result = await service.stop_plan(
            plan_id, confirmed=payload.confirmed, confirmed_by=payload.confirmed_by
        )
    except RecurringConfirmationRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RecurringPlanNotFoundError as e:
        raise HTTPException(status_code=404, detail="recurring run plan not found") from e
    except RecurringPlanNotStoppableError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return RecurringRunResponse(**result)


@router.post(
    "/paper-signal-recurring-runs/{plan_id}/activate",
    response_model=RecurringRunResponse,
)
async def activate_recurring_run(
    plan_id: int,
    payload: ActivateRecurringRunRequest,
    service: PaperSignalRecurringRunService = Depends(get_recurring_run_service),
) -> RecurringRunResponse:
    """prepared 계획을 active로 전환한다(상태 전환만 — 실행 아님).

    active 상태는 미래 디스패처의 후보 상태일 뿐입니다. 이 API는 SignalLog/주문/거래를 만들지 않습니다.
    scheduler/job은 여전히 비활성이며 디스패처는 존재하지 않습니다(M2.14B-2 별도 승인). 자격 재검증 실패는
    422, 같은 페어 active 중복은 409.
    """
    try:
        result = await service.activate_plan(
            plan_id, confirmed=payload.confirmed, confirmed_by=payload.confirmed_by
        )
    except RecurringConfirmationRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RecurringPlanNotFoundError as e:
        raise HTTPException(status_code=404, detail="recurring run plan not found") from e
    except RecurringPlanNotActivatableError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except DuplicateRecurringPlanError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except _VALIDATION_ERRORS as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return RecurringRunResponse(**result)


@router.post(
    "/paper-signal-recurring-runs/{plan_id}/tick-once",
    response_model=RecurringTickResponse,
)
async def tick_recurring_run_once(
    plan_id: int,
    payload: TickRecurringRunRequest,
    service: PaperSignalRecurringRunService = Depends(get_recurring_run_tick_service),
) -> RecurringTickResponse:
    """선택한 active 반복 계획을 1회 신호 기록한다(선택한 계획만 · SignalLog만).

    dispatcher 아님 · scheduler/job 시작 없음 · 전체 active 실행 아님. baseline/challenger 각각 1회
    평가(최대 2 SignalLog) · 주문 없음 · 거래 없음. completed_runs는 페어 tick 시도 횟수를 세며,
    max_runs 도달 시 status=completed. 자격 재검증 실패는 422, 미존재는 404.
    """
    try:
        result = await service.tick_plan_once(
            plan_id, confirmed=payload.confirmed, confirmed_by=payload.confirmed_by
        )
    except RecurringConfirmationRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RecurringPlanNotFoundError as e:
        raise HTTPException(status_code=404, detail="recurring run plan not found") from e
    except RecurringPlanNotTickableError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RecurringPlanExhaustedError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except _VALIDATION_ERRORS as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return RecurringTickResponse(**result)
