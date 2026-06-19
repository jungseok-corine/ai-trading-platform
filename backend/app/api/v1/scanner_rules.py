"""스캐너 룰(시장 감시 조건) API (C-2.23).

시장 감시 조건을 룰/버전으로 저장하고, 미리 계산된 facts에 대해 평가한다.
모두 메타데이터 작업이며 주문과 무관하다.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import MarketCode, ScannerRuleStatus
from app.services.scanner_service import (
    ScannerRuleNotFoundError,
    ScannerRuleVersionNotFoundError,
    ScannerService,
)
from app.trading.scanner.conditions import InvalidConditionError

router = APIRouter(prefix="/scanner-rules", tags=["scanner-rules"])


def get_service(session: AsyncSession = Depends(get_db)) -> ScannerService:
    return ScannerService(session)


# --- schemas ---------------------------------------------------------------
class RuleCreateRequest(BaseModel):
    name: str
    market: MarketCode = MarketCode.KR
    description: str | None = None


class RuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market: MarketCode
    name: str
    description: str | None
    enabled: bool
    created_at: datetime
    version_count: int = 0


class VersionCreateRequest(BaseModel):
    conditions: list[dict]
    change_description: str | None = None
    status: ScannerRuleStatus = ScannerRuleStatus.DRAFT


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scanner_rule_id: int
    version_no: int
    conditions: list
    status: ScannerRuleStatus
    change_description: str | None
    created_at: datetime
    updated_at: datetime


class VersionStatusUpdateRequest(BaseModel):
    status: ScannerRuleStatus


class EvaluateRequest(BaseModel):
    facts: dict[str, Any]


class EvaluateResponse(BaseModel):
    matched: bool
    matched_conditions: list[str]
    total: int
    score: int


# --- rules -----------------------------------------------------------------
@router.post("", response_model=RuleRead, status_code=201)
async def create_rule(
    payload: RuleCreateRequest, service: ScannerService = Depends(get_service)
) -> RuleRead:
    rule = await service.create_rule(payload.name, payload.market, payload.description)
    return RuleRead(
        id=rule.id,
        market=rule.market,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        created_at=rule.created_at,
        version_count=0,
    )


@router.get("", response_model=list[RuleRead])
async def list_rules(
    market: MarketCode | None = Query(default=None),
    service: ScannerService = Depends(get_service),
) -> list[RuleRead]:
    pairs = await service.list_rules(market=market)
    return [
        RuleRead(
            id=rule.id,
            market=rule.market,
            name=rule.name,
            description=rule.description,
            enabled=rule.enabled,
            created_at=rule.created_at,
            version_count=count,
        )
        for rule, count in pairs
    ]


# --- versions --------------------------------------------------------------
@router.post("/{rule_id}/versions", response_model=VersionRead, status_code=201)
async def create_version(
    rule_id: int,
    payload: VersionCreateRequest,
    service: ScannerService = Depends(get_service),
) -> VersionRead:
    try:
        version = await service.create_version(
            rule_id,
            conditions=payload.conditions,
            change_description=payload.change_description,
            status=payload.status,
        )
    except ScannerRuleNotFoundError as e:
        raise HTTPException(status_code=404, detail="scanner rule not found") from e
    except InvalidConditionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return VersionRead.model_validate(version)


@router.get("/{rule_id}/versions", response_model=list[VersionRead])
async def list_versions(
    rule_id: int,
    include_archived: bool = Query(default=False),
    service: ScannerService = Depends(get_service),
) -> list[VersionRead]:
    try:
        versions = await service.list_versions(rule_id, include_archived=include_archived)
    except ScannerRuleNotFoundError as e:
        raise HTTPException(status_code=404, detail="scanner rule not found") from e
    return [VersionRead.model_validate(v) for v in versions]


@router.patch("/{rule_id}/versions/{version_id}", response_model=VersionRead)
async def update_version_status(
    rule_id: int,
    version_id: int,
    payload: VersionStatusUpdateRequest,
    service: ScannerService = Depends(get_service),
) -> VersionRead:
    try:
        version = await service.update_version_status(rule_id, version_id, payload.status)
    except (ScannerRuleNotFoundError, ScannerRuleVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail="scanner rule version not found") from e
    return VersionRead.model_validate(version)


@router.post("/{rule_id}/versions/{version_id}/evaluate", response_model=EvaluateResponse)
async def evaluate_version(
    rule_id: int,
    version_id: int,
    payload: EvaluateRequest,
    service: ScannerService = Depends(get_service),
) -> EvaluateResponse:
    """저장된 룰 버전을 facts에 대해 평가한다 (룰 테스트/디버깅 용도)."""
    try:
        result = await service.evaluate(rule_id, version_id, payload.facts)
    except (ScannerRuleNotFoundError, ScannerRuleVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail="scanner rule version not found") from e
    return EvaluateResponse(
        matched=result.matched,
        matched_conditions=result.matched_conditions,
        total=result.total,
        score=result.score,
    )
