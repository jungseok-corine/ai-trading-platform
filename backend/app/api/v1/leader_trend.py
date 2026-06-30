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
