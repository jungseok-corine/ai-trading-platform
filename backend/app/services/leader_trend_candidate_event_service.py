"""LeaderTrendCandidateEvent service (M2.15G-4) — create policy 강제, **API 없음**.

research-only leader trend 후보 관찰 기록을 **명시적 manual create**로만 저장한다(create policy = M2.15G-3).
**매수 신호가 아니다.** market data/KIS/external fetch 0 · candidate scan 0 · AI 0 · order/trade/signal 0 ·
scheduler 0 · migration 실행 0 · API response 생성 0. DB write는 `leader_trend_candidate_events` insert만.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.leader_trend_candidate_event import (
    CANDIDATE_BUCKETS,
    WINDOW_BASES,
    LeaderTrendCandidateEvent,
)
from app.domain.repositories.leader_trend_candidate_event import (
    LeaderTrendCandidateEventRepository,
)

# create policy 상수(M2.15G-3).
ALLOWED_VALIDATION_STATUSES = ("matched", "minor_diff", "explained_major_diff")
REQUIRED_SCANNER_NAME = "leader_trend"
REQUIRED_DATA_SOURCE = "local_market_data"
REQUIRED_TIMEFRAME = "1d"
REQUIRED_UNIVERSE_SCOPE = "pilot_5"
_WILDCARDS = {"all", "*", "universe", "full"}


class LeaderTrendCandidateEventValidationError(ValueError):
    """create input이 create policy를 위반."""


class LeaderTrendCandidateEventDuplicateError(ValueError):
    """unique key가 이미 존재(중복 후보)."""


@dataclass
class LeaderTrendCandidateEventCreateInput:
    symbol: str
    detected_at: datetime
    reference_date: date
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
    low_52w_gain_pct: float | None
    drawdown_from_52w_high_pct: float | None
    window_basis: str
    data_source: str
    validation_source: str | None
    validation_status: str
    validation_report_path: str | None
    research_only: bool
    not_buy_signal: bool
    source_basis_note: str | None = None
    notes: str | None = None
    provenance_warning: str | None = None
    safety_warning: str | None = None


class LeaderTrendCandidateEventService:
    """create policy를 강제하는 서비스. **읽기/append-only · 주문/스케줄러 부작용 없음.**"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = LeaderTrendCandidateEventRepository(session)

    @staticmethod
    def _validate(inp: LeaderTrendCandidateEventCreateInput) -> None:
        def fail(msg: str) -> None:
            raise LeaderTrendCandidateEventValidationError(msg)

        # 안전 플래그(매수 신호 아님 강제).
        if inp.research_only is not True:
            fail("research_only must be true")
        if inp.not_buy_signal is not True:
            fail("not_buy_signal must be true")
        # 출처/스코프 강제.
        if inp.scanner_name != REQUIRED_SCANNER_NAME:
            fail(f"scanner_name must be {REQUIRED_SCANNER_NAME!r}")
        if not inp.scanner_version:
            fail("scanner_version is required")
        if inp.data_source != REQUIRED_DATA_SOURCE:
            fail(f"data_source must be {REQUIRED_DATA_SOURCE!r} (no direct KIS/external source)")
        if inp.timeframe != REQUIRED_TIMEFRAME:
            fail(f"timeframe must be {REQUIRED_TIMEFRAME!r}")
        if inp.universe_scope.lower() in _WILDCARDS:
            fail("wildcard/all/full/universe scope not allowed")
        if inp.universe_scope != REQUIRED_UNIVERSE_SCOPE:
            fail(f"universe_scope must be {REQUIRED_UNIVERSE_SCOPE!r}")
        # bucket / window_basis 허용값.
        if inp.candidate_bucket not in CANDIDATE_BUCKETS:
            fail(f"candidate_bucket must be one of {CANDIDATE_BUCKETS}")
        if not inp.window_basis:
            fail("window_basis is required")
        if inp.window_basis not in WINDOW_BASES:
            fail(f"window_basis must be one of {WINDOW_BASES}")
        # validation policy.
        if inp.validation_status not in ALLOWED_VALIDATION_STATUSES:
            fail(
                "validation_status must be one of "
                f"{ALLOWED_VALIDATION_STATUSES} (unresolved_major_diff/not_validated rejected)"
            )
        if not inp.validation_report_path:
            fail("validation_report_path is required")
        if inp.validation_status == "explained_major_diff" and not inp.source_basis_note:
            fail("explained_major_diff requires source_basis_note")

    async def create_research_event(
        self, inp: LeaderTrendCandidateEventCreateInput
    ) -> LeaderTrendCandidateEvent:
        """정책 검증 + 중복 검사 후 단일 record를 append. **주문/신호/스케줄러 부작용 없음.**"""
        self._validate(inp)
        if await self._repo.exists_by_unique_key(
            symbol=inp.symbol, scanner_name=inp.scanner_name, scanner_version=inp.scanner_version,
            reference_date=inp.reference_date, timeframe=inp.timeframe,
            window_basis=inp.window_basis, universe_scope=inp.universe_scope,
        ):
            raise LeaderTrendCandidateEventDuplicateError(
                "duplicate candidate event for unique key "
                "(symbol/scanner/version/reference_date/timeframe/window_basis/universe_scope)"
            )
        event = LeaderTrendCandidateEvent(
            symbol=inp.symbol, detected_at=inp.detected_at, reference_date=inp.reference_date,
            timeframe=inp.timeframe, universe_scope=inp.universe_scope,
            scanner_name=inp.scanner_name, scanner_version=inp.scanner_version,
            candidate_bucket=inp.candidate_bucket,
            is_operational_candidate=inp.is_operational_candidate,
            strategy_extreme=inp.strategy_extreme, current_price=inp.current_price,
            low_52w=inp.low_52w, high_52w=inp.high_52w,
            low_52w_gain_pct=inp.low_52w_gain_pct,
            drawdown_from_52w_high_pct=inp.drawdown_from_52w_high_pct,
            window_basis=inp.window_basis, data_source=inp.data_source,
            validation_source=inp.validation_source, validation_status=inp.validation_status,
            validation_report_path=inp.validation_report_path,
            research_only=True, not_buy_signal=True,
            source_basis_note=inp.source_basis_note, notes=inp.notes,
            provenance_warning=inp.provenance_warning, safety_warning=inp.safety_warning,
        )
        created = await self._repo.create(event)
        await self._session.commit()  # 단일 record append 후 커밋(주문/신호 부작용 없음)
        return created
