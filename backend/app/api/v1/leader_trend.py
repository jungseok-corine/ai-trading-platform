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

router = APIRouter(prefix="/leader-trend", tags=["leader-trend"])

_PROVENANCE = (
    "KIS-sourced daily data validated against KIS real-domain quotation/daily "
    "(M2.15D-2/3A); non-KIS independence unconfirmed."
)
_SAFETY = "Candidates are filters for research, not trading signals. NOT buy signals."
_WILDCARDS = {"all", "*", "universe", "full"}


def get_scanner(session: AsyncSession = Depends(get_db)) -> LeaderTrendScanner:
    return LeaderTrendScanner(session)


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
