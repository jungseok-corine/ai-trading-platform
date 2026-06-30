"""Leader Trend 후보 read-only 노출 API (M2.15D-3B).

이미 적재된 일봉(`market_data` 1d)만 읽어 LeaderTrendScanner로 52주 지표/후보를 계산해 **연구용**으로 노출한다.
**읽기 전용**: DB write 0 · 라이브 KIS 0 · 일봉 fetch 0 · SignalLog/Trade/Order 0 · broker/주문 0 · 스케줄러/
디스패처 0 · 후보 영속화 0. **후보는 매수 신호가 아니다**(필터·연구용). 기본 범위는 검증된 pilot 5종.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.db.session import get_db
from app.services.leader_trend_scanner import (
    MAX_SCAN_SYMBOLS,
    OPERATIONAL_CANDIDATE_BUCKETS,
    PILOT_SYMBOLS,
    LeaderTrendScanner,
)
from app.services.leader_trend_validation_service import (
    MAJOR_DIFF_PCT,
    MINOR_DIFF_PCT,
    LeaderTrendValidationService,
    db_52w_snapshot,
    window_basis_audit,
)

router = APIRouter(prefix="/leader-trend", tags=["leader-trend"])

_PROVENANCE = (
    "KIS-sourced daily data validated against KIS real-domain quotation/daily "
    "(M2.15D-2/3A); non-KIS independence unconfirmed."
)
_SAFETY = "Candidates are filters for research, not trading signals. NOT buy signals."
_WILDCARDS = {"all", "*", "universe", "full"}


def get_scanner(session: AsyncSession = Depends(get_db)) -> LeaderTrendScanner:
    return LeaderTrendScanner(session)


def get_validation_service(
    session: AsyncSession = Depends(get_db),
) -> LeaderTrendValidationService:
    return LeaderTrendValidationService(session)  # 기본 placeholder fixture 사용


_VALIDATION_SAFETY = (
    "This endpoint is read-only validation support. It is not a buy signal and must not be "
    "connected to trading."
)
_VALIDATION_PROVENANCE = (
    "Reference values are manually supplied non-KIS data (no external API auto-fetch). "
    "They are used only to validate data consistency, not for trading decisions."
)


def _parse_symbols(symbols: str | None) -> tuple[list[str] | None, str]:
    """공통: symbols 쿼리 파싱 + scope. wildcard/cap 거부."""
    if symbols is None:
        return None, "pilot_5"
    requested = [s.strip() for s in symbols.split(",") if s.strip()]
    if any(s.lower() in _WILDCARDS for s in requested):
        raise HTTPException(status_code=400, detail="wildcard/universe scope not allowed")
    if not requested:
        raise HTTPException(status_code=400, detail="no symbols provided")
    if len(requested) > MAX_SCAN_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"too many symbols (max {MAX_SCAN_SYMBOLS})")
    return requested, "explicit"


class LeaderTrendCandidateResult(BaseModel):
    symbol: str
    daily_count: int
    newest_date: str | None = None
    oldest_date: str | None = None
    current_close: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    low_52w_gain_pct: float | None = None
    drawdown_from_52w_high_pct: float | None = None
    ma20: float | None = None
    ma50: float | None = None
    recent_20d_high: float | None = None
    volume_20d_avg: int | None = None
    has_20: bool = False
    has_50: bool = False
    has_120: bool = False
    has_252: bool = False
    ready_for_52w: bool = False
    raw_candidate_a: bool = False
    raw_candidate_b: bool = False
    hard_errors: list[str] = []
    data_quality_warnings: list[str] = []
    adjustment_warnings: list[str] = []
    strategy_extreme_warnings: list[str] = []
    is_data_valid: bool = True
    is_adjustment_suspect: bool = False
    is_strategy_extreme: bool = False
    candidate_bucket_research: str
    candidate_bucket_operational: str
    candidate_bucket: str
    operationally_safe_for_classification: bool = False


class LeaderTrendCandidateResponse(BaseModel):
    scanned_at: str
    universe_scope: str
    research_only: bool
    not_buy_signal: bool
    provenance_warning: str
    safety_warning: str
    total_symbols_scanned: int
    total_operational_candidates: int
    candidates: list[LeaderTrendCandidateResult]
    results: list[LeaderTrendCandidateResult]


@router.get("/candidates", response_model=LeaderTrendCandidateResponse)
async def get_leader_trend_candidates(
    symbols: str | None = Query(
        default=None,
        description="comma-separated, max 5; default = validated pilot 5. NOT buy signals.",
    ),
    scanner: LeaderTrendScanner = Depends(get_scanner),
) -> LeaderTrendCandidateResponse:
    """Leader Trend 연구 후보(읽기 전용). **매수 신호 아님.** 기본 pilot 5종."""
    if symbols is None:
        universe = list(PILOT_SYMBOLS)
        scope = "pilot_5"
    else:
        requested = [s.strip() for s in symbols.split(",") if s.strip()]
        if any(s.lower() in _WILDCARDS for s in requested):
            raise HTTPException(status_code=400, detail="wildcard/universe scope not allowed")
        if not requested:
            raise HTTPException(status_code=400, detail="no symbols provided")
        if len(requested) > MAX_SCAN_SYMBOLS:
            raise HTTPException(
                status_code=400, detail=f"too many symbols (max {MAX_SCAN_SYMBOLS})"
            )
        universe = requested
        scope = "explicit"

    metrics = await scanner.scan(universe)
    results = [LeaderTrendCandidateResult(**m.to_dict()) for m in metrics]
    candidates = [
        r for r in results if r.candidate_bucket_operational in OPERATIONAL_CANDIDATE_BUCKETS
    ]
    return LeaderTrendCandidateResponse(
        scanned_at=datetime.now(KST).isoformat(),
        universe_scope=scope,
        research_only=True,
        not_buy_signal=True,
        provenance_warning=_PROVENANCE,
        safety_warning=_SAFETY,
        total_symbols_scanned=len(results),
        total_operational_candidates=len(candidates),
        candidates=candidates,
        results=results,
    )


# --- M2.15F-1: non-KIS 독립 52주 검증(읽기 전용 데이터 품질 · 매매 신호 아님) ---
class NonKisValidationResult(BaseModel):
    symbol: str
    validation_status: str
    db_reference_close: float | None = None
    db_high_52w: float | None = None
    db_low_52w: float | None = None
    reference_close: float | None = None
    reference_high_52w: float | None = None
    reference_low_52w: float | None = None
    reference_close_diff_pct: float | None = None
    high_52w_diff_pct: float | None = None
    low_52w_diff_pct: float | None = None
    note: str | None = None


class NonKisValidationResponse(BaseModel):
    scanned_at: str
    research_only: bool
    not_buy_signal: bool
    read_only: bool
    external_reference_auto_fetch: bool
    universe_scope: str
    total_symbols_checked: int
    minor_diff_threshold_pct: float
    major_diff_threshold_pct: float
    reference_source_name: str | None
    reference_source_note: str | None
    reference_as_of_date: str | None
    summary: dict[str, int]
    safety_warning: str
    provenance_warning: str
    results: list[NonKisValidationResult]


@router.get("/validation/non-kis-52w", response_model=NonKisValidationResponse)
async def get_non_kis_52w_validation(
    symbols: str | None = Query(
        default=None,
        description="comma-separated, max 5; default pilot_5. Read-only data-quality validation, NOT a buy signal.",
    ),
    service: LeaderTrendValidationService = Depends(get_validation_service),
) -> NonKisValidationResponse:
    """DB 52주 값 vs 수동 non-KIS 레퍼런스 비교(읽기 전용). **매매 신호 아님 · 외부 자동 호출 없음.**"""
    requested, _ = _parse_symbols(symbols)
    report = await service.validate(requested)
    return NonKisValidationResponse(
        scanned_at=datetime.now(KST).isoformat(),
        research_only=True,
        not_buy_signal=True,
        read_only=True,
        external_reference_auto_fetch=False,
        universe_scope=report.universe_scope,
        total_symbols_checked=len(report.results),
        minor_diff_threshold_pct=MINOR_DIFF_PCT,
        major_diff_threshold_pct=MAJOR_DIFF_PCT,
        reference_source_name=report.source_name,
        reference_source_note=report.source_note,
        reference_as_of_date=report.as_of_date,
        summary=report.summary(),
        safety_warning=_VALIDATION_SAFETY,
        provenance_warning=_VALIDATION_PROVENANCE,
        results=[NonKisValidationResult(**r.to_dict()) for r in report.results],
    )


# --- M2.15F-3A: DB-side 52주 snapshot export(읽기 전용 · 매수 신호 아님) ---
class DbSnapshotResultModel(BaseModel):
    symbol: str
    row_count: int
    first_date: str | None = None
    last_date: str | None = None
    db_reference_close: float | None = None
    db_reference_close_date: str | None = None
    db_high_52w: float | None = None
    db_high_52w_date: str | None = None
    db_low_52w: float | None = None
    db_low_52w_date: str | None = None
    low_52w_gain_pct: float | None = None
    drawdown_from_52w_high_pct: float | None = None
    candidate_bucket_if_any: str | None = None
    data_quality_note: str


class DbSnapshotResponse(BaseModel):
    generated_at: str
    research_only: bool
    not_buy_signal: bool
    read_only: bool
    external_reference_auto_fetch: bool
    kis_call_used: bool
    db_write_performed: bool
    universe_scope: str
    timeframe: str
    total_symbols_checked: int
    safety_warning: str
    provenance_warning: str
    results: list[DbSnapshotResultModel]


_DB_SNAPSHOT_SAFETY = (
    "This DB snapshot is validation support only. It is not a buy signal and must not be "
    "connected to trading."
)
_DB_SNAPSHOT_PROVENANCE = (
    "Values are computed only from existing local market_data. No external or KIS fetch is "
    "performed."
)


@router.get("/validation/db-52w-snapshot", response_model=DbSnapshotResponse)
async def get_db_52w_snapshot(
    symbols: str | None = Query(
        default=None,
        description="comma-separated, max 5; default pilot_5. Read-only local DB snapshot, NOT a buy signal.",
    ),
    session: AsyncSession = Depends(get_db),
) -> DbSnapshotResponse:
    """기존 market_data(1d)만으로 52주 기준값을 read-only export. **매매 신호 아님 · 외부/KIS 호출 없음.**"""
    requested, _ = _parse_symbols(symbols)
    report = await db_52w_snapshot(session, requested)
    return DbSnapshotResponse(
        generated_at=datetime.now(KST).isoformat(),
        research_only=True,
        not_buy_signal=True,
        read_only=True,
        external_reference_auto_fetch=False,
        kis_call_used=False,
        db_write_performed=False,
        universe_scope=report.universe_scope,
        timeframe=report.timeframe,
        total_symbols_checked=len(report.results),
        safety_warning=_DB_SNAPSHOT_SAFETY,
        provenance_warning=_DB_SNAPSHOT_PROVENANCE,
        results=[DbSnapshotResultModel(**r.to_dict()) for r in report.results],
    )


# --- M2.15F-3F: 52주 window basis audit(읽기 전용 · 매수 신호 아님) ---
class WindowBasisResultModel(BaseModel):
    basis: str
    row_count: int
    first_date: str | None = None
    last_date: str | None = None
    reference_close: float | None = None
    reference_close_date: str | None = None
    high_52w: float | None = None
    high_52w_date: str | None = None
    low_52w: float | None = None
    low_52w_date: str | None = None
    low_52w_gain_pct: float | None = None
    drawdown_from_52w_high_pct: float | None = None
    candidate_bucket_if_any: str | None = None


class WindowAuditRowModel(BaseModel):
    symbol: str
    last_252_trading_rows: WindowBasisResultModel
    calendar_52_weeks: WindowBasisResultModel
    high_diff_between_basis_pct: float | None = None
    low_diff_between_basis_pct: float | None = None
    reference_close_diff_between_basis_pct: float | None = None
    bucket_changed_between_basis: bool = False
    naver_low: float | None = None
    low_252_vs_naver_diff_pct: float | None = None
    low_calendar_vs_naver_diff_pct: float | None = None
    naver_major_diff_explainable_by_window_basis: str = "unknown"


class WindowBasisAuditResponse(BaseModel):
    generated_at: str
    research_only: bool
    not_buy_signal: bool
    read_only: bool
    external_reference_auto_fetch: bool
    kis_call_used: bool
    db_write_performed: bool
    candidate_event_allowed: bool
    universe_scope: str
    total_symbols_checked: int
    safety_warning: str
    provenance_warning: str
    results: list[WindowAuditRowModel]


_WINDOW_AUDIT_SAFETY = (
    "This window-basis audit is read-only validation support. It is not a buy signal and must not "
    "be connected to trading."
)
_WINDOW_AUDIT_PROVENANCE = (
    "Both bases are computed only from existing local market_data. No external or KIS fetch is "
    "performed. Explainability is a hypothesis, not DB-correction or CandidateEvent approval."
)


@router.get("/validation/52w-window-basis-audit", response_model=WindowBasisAuditResponse)
async def get_52w_window_basis_audit(
    symbols: str | None = Query(
        default=None,
        description="comma-separated, max 5; default pilot_5. Read-only window-basis audit, NOT a buy signal.",
    ),
    service: LeaderTrendValidationService = Depends(get_validation_service),
    session: AsyncSession = Depends(get_db),
) -> WindowBasisAuditResponse:
    """last_252_trading_rows vs calendar_52_weeks 비교(읽기 전용). **매매 신호 아님 · 외부/KIS 호출 없음.**"""
    requested, scope = _parse_symbols(symbols)
    rows = await window_basis_audit(session, service._reference, requested)
    return WindowBasisAuditResponse(
        generated_at=datetime.now(KST).isoformat(),
        research_only=True,
        not_buy_signal=True,
        read_only=True,
        external_reference_auto_fetch=False,
        kis_call_used=False,
        db_write_performed=False,
        candidate_event_allowed=False,
        universe_scope=scope if requested else "pilot_5",
        total_symbols_checked=len(rows),
        safety_warning=_WINDOW_AUDIT_SAFETY,
        provenance_warning=_WINDOW_AUDIT_PROVENANCE,
        results=[WindowAuditRowModel(**r.to_dict()) for r in rows],
    )


# --- M2.15G-5: explicit manual LeaderTrendCandidateEvent create API(매수 신호 아님) ---
from datetime import date as _date  # noqa: E402

from app.services.leader_trend_candidate_event_service import (  # noqa: E402
    LeaderTrendCandidateEventCreateInput,
    LeaderTrendCandidateEventDuplicateError,
    LeaderTrendCandidateEventService,
    LeaderTrendCandidateEventValidationError,
)

_LTCE_SAFETY = (
    "This event is a research-only observation. It must not be connected to trading, orders, "
    "signals, or recommendations."
)
_LTCE_NOT_BUY = "This is not a buy signal, sell signal, or investment recommendation."


def get_ltce_service(
    session: AsyncSession = Depends(get_db),
) -> LeaderTrendCandidateEventService:
    return LeaderTrendCandidateEventService(session)


class LeaderTrendCandidateEventCreateRequest(BaseModel):
    symbol: str
    detected_at: datetime
    reference_date: _date
    timeframe: str
    universe_scope: str
    scanner_name: str
    scanner_version: str
    candidate_bucket: str
    is_operational_candidate: bool
    strategy_extreme: bool
    current_price: float
    low_52w: float
    high_52w: float
    low_52w_gain_pct: float | None = None
    drawdown_from_52w_high_pct: float | None = None
    window_basis: str
    data_source: str
    validation_source: str | None = None
    validation_status: str
    validation_report_path: str | None = None
    research_only: bool
    not_buy_signal: bool
    source_basis_note: str | None = None
    notes: str | None = None
    provenance_warning: str | None = None
    safety_warning: str | None = None


class LeaderTrendCandidateEventCreateResponse(BaseModel):
    id: int
    symbol: str
    reference_date: _date
    candidate_bucket: str
    validation_status: str
    research_only: bool
    not_buy_signal: bool
    safety_warning: str
    not_buy_signal_warning: str
    created_at: datetime


@router.post(
    "/candidate-events/research-only",
    response_model=LeaderTrendCandidateEventCreateResponse,
    status_code=201,
)
async def create_leader_trend_candidate_event(
    payload: LeaderTrendCandidateEventCreateRequest,
    service: LeaderTrendCandidateEventService = Depends(get_ltce_service),
) -> LeaderTrendCandidateEventCreateResponse:
    """Leader trend research candidate를 **명시적 수동**으로 1건 기록(매수 신호 아님).

    service가 create policy의 source of truth — 자동/bulk/스케줄러 저장 없음, 주문/거래/신호 미연결.
    """
    inp = LeaderTrendCandidateEventCreateInput(
        symbol=payload.symbol, detected_at=payload.detected_at,
        reference_date=payload.reference_date, timeframe=payload.timeframe,
        universe_scope=payload.universe_scope, scanner_name=payload.scanner_name,
        scanner_version=payload.scanner_version, candidate_bucket=payload.candidate_bucket,
        is_operational_candidate=payload.is_operational_candidate,
        strategy_extreme=payload.strategy_extreme, current_price=payload.current_price,
        low_52w=payload.low_52w, high_52w=payload.high_52w,
        low_52w_gain_pct=payload.low_52w_gain_pct,
        drawdown_from_52w_high_pct=payload.drawdown_from_52w_high_pct,
        window_basis=payload.window_basis, data_source=payload.data_source,
        validation_source=payload.validation_source, validation_status=payload.validation_status,
        validation_report_path=payload.validation_report_path,
        research_only=payload.research_only, not_buy_signal=payload.not_buy_signal,
        source_basis_note=payload.source_basis_note, notes=payload.notes,
        provenance_warning=payload.provenance_warning, safety_warning=payload.safety_warning,
    )
    try:
        ev = await service.create_research_event(inp)
    except LeaderTrendCandidateEventDuplicateError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except LeaderTrendCandidateEventValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return LeaderTrendCandidateEventCreateResponse(
        id=ev.id, symbol=ev.symbol, reference_date=ev.reference_date,
        candidate_bucket=ev.candidate_bucket, validation_status=ev.validation_status,
        research_only=ev.research_only, not_buy_signal=ev.not_buy_signal,
        safety_warning=_LTCE_SAFETY, not_buy_signal_warning=_LTCE_NOT_BUY,
        created_at=ev.created_at,
    )
