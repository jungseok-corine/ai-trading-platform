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
from app.services.candidate_outcome_service import CandidateOutcomeService
from app.services.candidate_proposal_experiment_service import (
    CandidateProposalExperimentService,
    ProposalNotApprovedError,
)
from app.services.candidate_proposal_experiment_service import (
    ProposalNotFoundError as ExperimentProposalNotFoundError,
)
from app.services.candidate_service import CandidateService
from app.services.candidate_strategy_proposal_service import (
    CandidateNotFoundError,
    CandidateStrategyProposalService,
    InvalidReviewStatusError,
    InvalidStrategyTypeError,
    ProposalNotFoundError,
)
from app.services.scanner_scan_service import ScannerScanService
from app.services.scanner_service import ScannerRuleVersionNotFoundError

router = APIRouter(tags=["candidates"])


def get_service(session: AsyncSession = Depends(get_db)) -> CandidateService:
    return CandidateService(session)


def get_scan_service(session: AsyncSession = Depends(get_db)) -> ScannerScanService:
    return ScannerScanService(session)


def get_outcome_service(session: AsyncSession = Depends(get_db)) -> CandidateOutcomeService:
    return CandidateOutcomeService(session)


def get_proposal_service(
    session: AsyncSession = Depends(get_db),
) -> CandidateStrategyProposalService:
    return CandidateStrategyProposalService(session)


def get_proposal_experiment_service(
    session: AsyncSession = Depends(get_db),
) -> CandidateProposalExperimentService:
    return CandidateProposalExperimentService(session)


class CandidateAnalysisRead(BaseModel):
    horizon_minutes: int
    total: int
    analyzed: int
    overall: dict
    by_time_bucket: dict
    by_condition: dict


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


@router.get("/candidates/analysis", response_model=CandidateAnalysisRead)
async def analyze_candidates(
    scanner_rule_version_id: int | None = Query(default=None),
    horizon_minutes: int = Query(default=30, ge=1, le=1440),
    service: CandidateOutcomeService = Depends(get_outcome_service),
) -> CandidateAnalysisRead:
    """후보 발견 이후 forward 수익률을 계산해 조건·시간대별 성과를 집계한다."""
    result = await service.analyze(
        scanner_rule_version_id=scanner_rule_version_id, horizon_minutes=horizon_minutes
    )
    return CandidateAnalysisRead(
        horizon_minutes=result.horizon_minutes,
        total=result.total,
        analyzed=result.analyzed,
        overall=result.overall,
        by_time_bucket=result.by_time_bucket,
        by_condition=result.by_condition,
    )


class StrategyProposalCreateRequest(BaseModel):
    # 모두 선택. 미지정 시 후보 matched_conditions/score에서 안전한 기본값을 유추한다.
    suggested_strategy_type: str | None = None
    rationale: str | None = None
    confidence: float | None = None
    suggested_parameters: dict | None = None


class StrategyProposalReviewRequest(BaseModel):
    status: str  # approved | rejected (실행 없음, 상태만 변경)
    reviewed_by: str | None = None
    review_note: str | None = None


class CandidateStrategyProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_event_id: int
    symbol_code: str
    suggested_strategy_type: str
    rationale: str | None
    confidence: float | None
    suggested_parameters: dict | None
    status: str
    source: str
    reviewed_at: datetime | None
    reviewed_by: str | None
    review_note: str | None
    experiment_id: int | None
    prepared_at: datetime | None
    created_at: datetime


@router.post(
    "/candidates/{candidate_event_id}/strategy-proposals",
    response_model=CandidateStrategyProposalRead,
    status_code=201,
)
async def create_candidate_strategy_proposal(
    candidate_event_id: int,
    payload: StrategyProposalCreateRequest | None = None,
    service: CandidateStrategyProposalService = Depends(get_proposal_service),
) -> CandidateStrategyProposalRead:
    """후보에 대한 PENDING 전략 제안을 저장한다(제안만 — 실행/배정/버전 생성 없음)."""
    body = payload or StrategyProposalCreateRequest()
    try:
        proposal = await service.create(
            candidate_event_id,
            suggested_strategy_type=body.suggested_strategy_type,
            rationale=body.rationale,
            confidence=body.confidence,
            suggested_parameters=body.suggested_parameters,
        )
    except CandidateNotFoundError as e:
        raise HTTPException(status_code=404, detail="candidate event not found") from e
    except InvalidStrategyTypeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return CandidateStrategyProposalRead.model_validate(proposal)


@router.get(
    "/candidates/{candidate_event_id}/strategy-proposals",
    response_model=list[CandidateStrategyProposalRead],
)
async def list_candidate_strategy_proposals(
    candidate_event_id: int,
    service: CandidateStrategyProposalService = Depends(get_proposal_service),
) -> list[CandidateStrategyProposalRead]:
    proposals = await service.list_for_candidate(candidate_event_id)
    return [CandidateStrategyProposalRead.model_validate(p) for p in proposals]


@router.get(
    "/candidate-strategy-proposals",
    response_model=list[CandidateStrategyProposalRead],
)
async def list_recent_candidate_strategy_proposals(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: CandidateStrategyProposalService = Depends(get_proposal_service),
) -> list[CandidateStrategyProposalRead]:
    proposals = await service.list_recent(status=status, limit=limit, offset=offset)
    return [CandidateStrategyProposalRead.model_validate(p) for p in proposals]


@router.patch(
    "/candidate-strategy-proposals/{proposal_id}/review",
    response_model=CandidateStrategyProposalRead,
)
async def review_candidate_strategy_proposal(
    proposal_id: int,
    payload: StrategyProposalReviewRequest,
    service: CandidateStrategyProposalService = Depends(get_proposal_service),
) -> CandidateStrategyProposalRead:
    """제안 상태만 approved/rejected로 갱신한다. 어떤 실행/배정/버전 생성도 하지 않는다."""
    try:
        proposal = await service.review(
            proposal_id,
            status=payload.status,
            reviewed_by=payload.reviewed_by,
            review_note=payload.review_note,
        )
    except ProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail="proposal not found") from e
    except InvalidReviewStatusError as e:
        raise HTTPException(
            status_code=422, detail="status must be 'approved' or 'rejected'"
        ) from e
    return CandidateStrategyProposalRead.model_validate(proposal)


class PreparedExperimentRead(BaseModel):
    proposal_id: int
    candidate_event_id: int
    symbol_code: str
    suggested_strategy_type: str
    strategy_id: int | None
    strategy_version_id: int | None
    strategy_version_status: str  # 항상 'draft' (ACTIVE 아님)
    experiment_id: int
    experiment_status: str  # 항상 'draft' (RUNNING 아님)
    auto_trade_enabled: bool  # 항상 False
    prepared_at: str | None
    already_prepared: bool


@router.post(
    "/candidate-strategy-proposals/{proposal_id}/prepare-paper-experiment",
    response_model=PreparedExperimentRead,
    status_code=201,
)
async def prepare_paper_experiment(
    proposal_id: int,
    service: CandidateProposalExperimentService = Depends(get_proposal_experiment_service),
) -> PreparedExperimentRead:
    """APPROVED 제안에서 DRAFT paper 실험 골격을 준비한다(실행 아님).

    실험을 돌리지 않는다. StrategyVersion/Experiment 모두 DRAFT, auto_trade=False.
    PENDING/REJECTED 제안은 422. 이미 준비된 제안은 기존 결과(idempotent).
    """
    try:
        result = await service.prepare(proposal_id)
    except ExperimentProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail="proposal not found") from e
    except ProposalNotApprovedError as e:
        raise HTTPException(
            status_code=422, detail="proposal must be approved before preparing an experiment"
        ) from e
    return PreparedExperimentRead(**result.__dict__)


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
