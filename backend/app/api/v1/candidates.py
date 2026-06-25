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
    ConfirmationRequiredError,
    InvalidExperimentStateError,
    NotPreparedError,
    ProposalNotApprovedError,
    UnexpectedAutoTradeError,
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
from app.services.paper_signal_analysis_input_service import (
    PaperSignalAnalysisInputService,
)
from app.services.paper_signal_outcome_service import (
    InvalidHorizonError,
    PaperSignalOutcomeService,
)
from app.services.paper_signal_outcome_service import (
    SessionNotFoundError as OutcomeSessionNotFoundError,
)
from app.services.paper_signal_service import (
    ConfirmationRequiredError as PaperConfirmationRequiredError,
)
from app.services.paper_signal_service import (
    DuplicateActiveSessionError,
    InvalidVersionStateError,
    NotReadyError,
    PaperSignalService,
    SessionNotFoundError,
)
from app.services.paper_signal_service import (
    NotPreparedError as PaperNotPreparedError,
)
from app.services.paper_signal_service import (
    ProposalNotApprovedError as PaperProposalNotApprovedError,
)
from app.services.paper_signal_service import (
    ProposalNotFoundError as PaperProposalNotFoundError,
)
from app.services.paper_signal_service import (
    UnexpectedAutoTradeError as PaperUnexpectedAutoTradeError,
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


def get_paper_signal_service(
    session: AsyncSession = Depends(get_db),
) -> PaperSignalService:
    # signal_service 없이 생성 — 시작/중지/조회 전용(run_due_sessions는 스케줄러 잡에서만).
    return PaperSignalService(session)


def get_paper_signal_outcome_service(
    session: AsyncSession = Depends(get_db),
) -> PaperSignalOutcomeService:
    return PaperSignalOutcomeService(session)


def get_paper_signal_analysis_input_service(
    session: AsyncSession = Depends(get_db),
) -> PaperSignalAnalysisInputService:
    return PaperSignalAnalysisInputService(session)


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


class ApprovePaperReadinessRequest(BaseModel):
    confirmed: bool = False
    confirmed_by: str | None = None


class ReadinessResultRead(BaseModel):
    proposal_id: int
    experiment_id: int
    experiment_status: str  # 항상 draft (변경 안 함)
    strategy_version_ids: list[int]
    strategy_version_statuses: list[str]  # 모두 draft (변경 안 함)
    auto_trade_enabled_values: list[bool]  # 모두 false
    ready: bool
    already_ready: bool
    ready_at: str | None
    ready_by: str | None
    message: str


@router.post(
    "/candidate-strategy-proposals/{proposal_id}/approve-paper-readiness",
    response_model=ReadinessResultRead,
)
async def approve_paper_readiness(
    proposal_id: int,
    payload: ApprovePaperReadinessRequest,
    service: CandidateProposalExperimentService = Depends(get_proposal_experiment_service),
) -> ReadinessResultRead:
    """준비된 DRAFT 실험을 'paper 테스트 준비됨'으로 **승인 기록만** 한다. 상태 전환 없음.

    confirmed=true + confirmed_by 필수. StrategyVersion/Experiment는 DRAFT 그대로 유지되어
    runner가 절대 잡지 않는다(신호 생성 없음). 주문/자동매매/브로커 호출 없음.
    DRAFT 준비 실험만 승인 가능, 이미 승인됐으면 idempotent.
    """
    try:
        result = await service.approve_paper_testing_readiness(
            proposal_id, confirmed=payload.confirmed, confirmed_by=payload.confirmed_by
        )
    except ExperimentProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail="proposal not found") from e
    except ConfirmationRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ProposalNotApprovedError as e:
        raise HTTPException(status_code=422, detail="proposal must be approved") from e
    except NotPreparedError as e:
        raise HTTPException(
            status_code=422, detail="prepare a paper experiment before approving readiness"
        ) from e
    except InvalidExperimentStateError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except UnexpectedAutoTradeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return ReadinessResultRead(**result.__dict__)


# --- Paper Signal Sessions (signal-only) -------------------------------------
class StartPaperSignalSessionRequest(BaseModel):
    confirmed: bool = False
    confirmed_by: str | None = None


class StopPaperSignalSessionRequest(BaseModel):
    confirmed_by: str | None = None
    note: str | None = None


class PaperSignalSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_strategy_proposal_id: int
    experiment_id: int | None
    strategy_version_id: int | None
    candidate_event_id: int | None
    symbol_code: str
    status: str  # active | stopped
    started_by: str
    started_at: datetime
    stopped_at: datetime | None
    stopped_by: str | None
    last_run_at: datetime | None
    last_error: str | None
    run_count: int
    signal_count: int
    note: str | None
    created_at: datetime


@router.post(
    "/candidate-strategy-proposals/{proposal_id}/paper-signal-sessions",
    response_model=PaperSignalSessionRead,
    status_code=201,
)
async def start_paper_signal_session(
    proposal_id: int,
    payload: StartPaperSignalSessionRequest,
    service: PaperSignalService = Depends(get_paper_signal_service),
) -> PaperSignalSessionRead:
    """준비·준비승인된 제안에 대해 active 신호 기록 세션을 시작한다. **주문/자동매매 아님.**

    SignalLog만 기록하는 전용 잡이 처리한다. StrategyVersion은 DRAFT 유지(상태 전환 없음).
    confirmed=true + confirmed_by + readiness 승인 + 준비된 실험 필요.
    """
    try:
        session_row = await service.start_session_from_candidate_strategy_proposal(
            proposal_id, confirmed=payload.confirmed, confirmed_by=payload.confirmed_by
        )
    except PaperProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail="proposal not found") from e
    except PaperConfirmationRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PaperProposalNotApprovedError as e:
        raise HTTPException(status_code=422, detail="proposal must be approved") from e
    except NotReadyError as e:
        raise HTTPException(
            status_code=422, detail="approve paper readiness before starting a signal session"
        ) from e
    except PaperNotPreparedError as e:
        raise HTTPException(
            status_code=422, detail="prepare a paper experiment before starting a signal session"
        ) from e
    except InvalidVersionStateError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PaperUnexpectedAutoTradeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except DuplicateActiveSessionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return PaperSignalSessionRead.model_validate(session_row)


@router.get("/paper-signal-sessions", response_model=list[PaperSignalSessionRead])
async def list_paper_signal_sessions(
    status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: PaperSignalService = Depends(get_paper_signal_service),
) -> list[PaperSignalSessionRead]:
    sessions = await service.list_sessions(status=status, limit=limit, offset=offset)
    return [PaperSignalSessionRead.model_validate(s) for s in sessions]


@router.post(
    "/paper-signal-sessions/{session_id}/stop",
    response_model=PaperSignalSessionRead,
)
async def stop_paper_signal_session(
    session_id: int,
    payload: StopPaperSignalSessionRequest,
    service: PaperSignalService = Depends(get_paper_signal_service),
) -> PaperSignalSessionRead:
    """active 세션을 중지한다. 이후 신호가 더 쌓이지 않는다. 상태 전환/주문 없음."""
    try:
        session_row = await service.stop_session(
            session_id, confirmed_by=payload.confirmed_by, note=payload.note
        )
    except PaperConfirmationRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail="session not found") from e
    return PaperSignalSessionRead.model_validate(session_row)


@router.get("/paper-signal-sessions/{session_id}/outcomes")
async def get_paper_signal_session_outcomes(
    session_id: int,
    horizon_minutes: int = Query(default=30),
    service: PaperSignalOutcomeService = Depends(get_paper_signal_outcome_service),
) -> dict:
    """세션이 만든 SignalLog의 forward 수익률을 집계한다 (읽기 전용 — 주문/실행 아님)."""
    try:
        board = await service.session_outcomes(session_id, horizon_minutes=horizon_minutes)
    except OutcomeSessionNotFoundError as e:
        raise HTTPException(status_code=404, detail="session not found") from e
    except InvalidHorizonError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return board.to_dict()


@router.get("/paper-signal-sessions/{session_id}/analysis-input")
async def get_paper_signal_session_analysis_input(
    session_id: int,
    horizon_minutes: int = Query(default=30),
    service: PaperSignalAnalysisInputService = Depends(get_paper_signal_analysis_input_service),
) -> dict:
    """세션의 AI 분석 입력(payload)을 만든다 (읽기 전용 — AI 호출/제안 생성 없음, DB 쓰기 없음)."""
    try:
        payload = await service.build_input(session_id, horizon_minutes=horizon_minutes)
    except OutcomeSessionNotFoundError as e:
        raise HTTPException(status_code=404, detail="session not found") from e
    except InvalidHorizonError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return payload.to_dict()


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
