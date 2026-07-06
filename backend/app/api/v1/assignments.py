"""전략 배정 규칙(Strategy Assignment) API (C-2.25).

후보 종목(candidate_event)에 전략을 배정하는 규칙을 관리하고, 배정을 수행해 로그를 남긴다.
이 단계에서는 strategy_version을 자동 생성하지 않는다. 모두 주문과 무관하다.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import MarketCode
from app.services.assignment_service import (
    AssignmentService,
    CandidateEventNotFoundError,
    InvalidStrategyTypeError,
)

router = APIRouter(tags=["assignments"])


def get_service(session: AsyncSession = Depends(get_db)) -> AssignmentService:
    return AssignmentService(session)


class AssignmentRuleCreateRequest(BaseModel):
    name: str
    strategy_type: str
    market: MarketCode = MarketCode.KR
    scanner_rule_id: int | None = None
    default_parameters: dict | None = None
    priority: int = 0
    description: str | None = None


class AssignmentRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market: MarketCode
    name: str
    description: str | None
    scanner_rule_id: int | None
    strategy_type: str
    default_parameters: dict | None
    priority: int
    enabled: bool
    created_at: datetime


class AssignmentLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_event_id: int
    strategy_assignment_rule_id: int | None
    market: MarketCode
    symbol_code: str
    strategy_type: str
    assigned_parameters: dict | None
    symbol_trendiness: str | None = None  # C-6.22: trend/range/unknown (매칭 off면 NULL)
    created_at: datetime


@router.post("/assignment-rules", response_model=AssignmentRuleRead, status_code=201)
async def create_assignment_rule(
    payload: AssignmentRuleCreateRequest,
    service: AssignmentService = Depends(get_service),
) -> AssignmentRuleRead:
    try:
        rule = await service.create_rule(
            name=payload.name,
            strategy_type=payload.strategy_type,
            market=payload.market,
            scanner_rule_id=payload.scanner_rule_id,
            default_parameters=payload.default_parameters,
            priority=payload.priority,
            description=payload.description,
        )
    except InvalidStrategyTypeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return AssignmentRuleRead.model_validate(rule)


@router.get("/assignment-rules", response_model=list[AssignmentRuleRead])
async def list_assignment_rules(
    market: MarketCode | None = Query(default=None),
    service: AssignmentService = Depends(get_service),
) -> list[AssignmentRuleRead]:
    rules = await service.list_rules(market=market)
    return [AssignmentRuleRead.model_validate(r) for r in rules]


@router.post("/candidates/{candidate_id}/assign", response_model=AssignmentLogRead)
async def assign_candidate(
    candidate_id: int,
    service: AssignmentService = Depends(get_service),
):
    """후보에 매칭되는 배정 규칙으로 전략을 배정하고 로그를 반환한다.

    매칭되는 규칙이 없으면 204(No Content)를 반환한다.
    """
    try:
        log = await service.assign(candidate_id)
    except CandidateEventNotFoundError as e:
        raise HTTPException(status_code=404, detail="candidate event not found") from e
    if log is None:
        # Response 객체를 직접 반환하면 response_model 검증을 우회한다.
        return Response(status_code=204)
    return AssignmentLogRead.model_validate(log)


@router.get("/assignment-logs", response_model=list[AssignmentLogRead])
async def list_assignment_logs(
    candidate_event_id: int | None = Query(default=None),
    symbol_code: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: AssignmentService = Depends(get_service),
) -> list[AssignmentLogRead]:
    logs = await service.list_logs(
        candidate_event_id=candidate_event_id,
        symbol_code=symbol_code,
        limit=limit,
        offset=offset,
    )
    return [AssignmentLogRead.model_validate(log) for log in logs]
