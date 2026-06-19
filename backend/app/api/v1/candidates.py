"""후보 종목(Candidate Event) API (C-2.24).

스캐너 룰 버전을 종목별 facts에 대해 평가해 매칭된 종목을 candidate_event로 기록하고,
기록된 후보를 조회한다. 모두 메타데이터 작업이며 주문과 무관하다.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import MarketCode
from app.services.candidate_service import CandidateService
from app.services.scanner_scan_service import ScannerScanService
from app.services.scanner_service import ScannerRuleVersionNotFoundError

router = APIRouter(tags=["candidates"])


def get_service(session: AsyncSession = Depends(get_db)) -> CandidateService:
    return CandidateService(session)


def get_scan_service(session: AsyncSession = Depends(get_db)) -> ScannerScanService:
    return ScannerScanService(session)


class ScanRequest(BaseModel):
    symbol_facts: dict[str, dict[str, Any]]
    triggered_at: datetime | None = None
    context_snapshot_id: int | None = None


class ScanMarketRequest(BaseModel):
    symbol_codes: list[str]
    timeframe: str = "1m"
    volume_window: int = 20
    lookback: int = 60
    context_snapshot_id: int | None = None


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scanner_rule_version_id: int
    market: MarketCode
    symbol_code: str
    triggered_at: datetime
    score: int
    matched_conditions: list | None
    facts: dict | None
    context_snapshot_id: int | None
    created_at: datetime


class ScanResponse(BaseModel):
    scanner_rule_version_id: int
    scanned: int
    matched: int
    candidates: list[CandidateRead]


@router.post(
    "/scanner-rules/{rule_id}/versions/{version_id}/scan",
    response_model=ScanResponse,
    status_code=201,
)
async def scan(
    rule_id: int,
    version_id: int,
    payload: ScanRequest,
    service: CandidateService = Depends(get_service),
) -> ScanResponse:
    """룰 버전을 종목별 facts에 대해 평가하고 매칭된 종목을 후보로 기록한다.

    rule_id는 경로 일관성을 위해 받지만, 평가 대상은 version_id이다.
    """
    try:
        result = await service.scan(
            version_id,
            symbol_facts=payload.symbol_facts,
            triggered_at=payload.triggered_at,
            context_snapshot_id=payload.context_snapshot_id,
        )
    except ScannerRuleVersionNotFoundError as e:
        raise HTTPException(status_code=404, detail="scanner rule version not found") from e
    return ScanResponse(
        scanner_rule_version_id=result.scanner_rule_version_id,
        scanned=result.scanned,
        matched=result.matched,
        candidates=[CandidateRead.model_validate(c) for c in result.candidates],
    )


@router.post(
    "/scanner-rules/{rule_id}/versions/{version_id}/scan-market",
    response_model=ScanResponse,
    status_code=201,
)
async def scan_market(
    rule_id: int,
    version_id: int,
    payload: ScanMarketRequest,
    service: ScannerScanService = Depends(get_scan_service),
) -> ScanResponse:
    """DB의 시장 데이터/수급으로 종목 facts를 계산해 룰을 실행하고 후보를 기록한다.

    수동 facts를 넣는 /scan과 달리, 시스템이 facts를 계산한다(실제 데이터로 도는 경로).
    """
    try:
        result = await service.scan_from_market_data(
            version_id,
            symbol_codes=payload.symbol_codes,
            timeframe=payload.timeframe,
            volume_window=payload.volume_window,
            lookback=payload.lookback,
            context_snapshot_id=payload.context_snapshot_id,
        )
    except ScannerRuleVersionNotFoundError as e:
        raise HTTPException(status_code=404, detail="scanner rule version not found") from e
    return ScanResponse(
        scanner_rule_version_id=result.scanner_rule_version_id,
        scanned=result.scanned,
        matched=result.matched,
        candidates=[CandidateRead.model_validate(c) for c in result.candidates],
    )


@router.get("/candidates", response_model=list[CandidateRead])
async def list_candidates(
    scanner_rule_version_id: int | None = Query(default=None),
    symbol_code: str | None = Query(default=None),
    market: MarketCode | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: CandidateService = Depends(get_service),
) -> list[CandidateRead]:
    candidates = await service.list_candidates(
        scanner_rule_version_id=scanner_rule_version_id,
        symbol_code=symbol_code,
        market=market,
        limit=limit,
        offset=offset,
    )
    return [CandidateRead.model_validate(c) for c in candidates]
