"""Pair-Scoped Recurring Signal Run Plan API (M2.14A — inert plan management).

계획을 **생성·조회·중지**만 한다. 생성된 계획은 실행되지 않는다(prepared only):
주문/거래/SignalLog 없음 · 스케줄러/잡 미활성 · 디스패처 없음(M2.14B 별도 승인). D-24 참조.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
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
    RecurringPlanNotActivatableError,
    RecurringPlanNotFoundError,
    RecurringPlanNotStoppableError,
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

router = APIRouter(tags=["paper-signal-recurring-runs"])


def get_recurring_run_service(
    session: AsyncSession = Depends(get_db),
) -> PaperSignalRecurringRunService:
    # 실행 경로 없음 — broker/SignalService를 주입하지 않는다(계획 관리 전용).
    return PaperSignalRecurringRunService(session)


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


class RecurringRunResponse(BaseModel):
    id: int
    status: str  # prepared | active | stopped | (미래: completed/failed)
    scope_type: str
    baseline_session_id: int
    challenger_session_id: int
    interval_seconds: int
    max_runs: int
    completed_runs: int
    last_run_at: datetime | None
    next_run_at: datetime | None  # M2.14A에서는 항상 None
    created_by: str
    stopped_by: str | None
    stopped_at: datetime | None
    note: str | None
    last_error: str | None
    orders_created: int  # 항상 0
    trades_created: int  # 항상 0
    warnings: list[str]


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
