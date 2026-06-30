"""Non-KIS 독립 52주 검증 하네스 (M2.15F-1) — **읽기 전용 데이터 품질 검증**.

기존 `market_data`(timeframe="1d")에서 종목별 52주 high/low/current close를 계산하고, **사람이 수동으로 채운
non-KIS 레퍼런스 fixture** 값과 비교한다. **외부 API 자동 호출 없음 · 웹 크롤링 없음 · KIS live/paper 호출 없음 ·
DB write 없음 · CandidateEvent/SignalLog/Trade/Order 없음 · 스케줄러 없음.**

⚠ 본 검증은 **데이터 품질 확인**이며 **매매 신호가 아니다.** threshold는 검증 보조 기준이지 매매 판단 기준이
아니다. 검증을 통과해도 실거래가 허용되는 것은 아니다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.models.market_data import MarketData
from app.services.leader_trend_scanner import (
    MAX_SCAN_SYMBOLS,
    PILOT_SYMBOLS,
    compute_metrics,
)

DAILY_TIMEFRAME = "1d"

# 검증 보조 임계값(매매 판단 아님 · 데이터 품질 비교용).
MINOR_DIFF_PCT = 0.7   # |diff| <= 0.7% → matched
MAJOR_DIFF_PCT = 2.0   # 0.7% < |diff| <= 2.0% → minor_diff, > 2.0% → major_diff

# Runtime 기본 = 사람이 채우는 manual snapshot(app/data/reference). 테스트 디렉토리에 의존하지 않는다.
# (테스트는 synthetic dict 또는 test fixture를 명시 주입한다.)
_DEFAULT_REFERENCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data" / "reference" / "non_kis_52w_reference_pilot5.manual.json"
)


@dataclass
class SymbolValidation:
    symbol: str
    validation_status: str  # matched|minor_diff|major_diff|missing_db_data|missing_reference_data|placeholder_reference
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

    def to_dict(self) -> dict:
        return {**self.__dict__}


@dataclass
class ValidationReport:
    universe_scope: str
    symbols: list[str]
    source_name: str | None
    source_note: str | None
    as_of_date: str | None
    results: list[SymbolValidation] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        keys = ("matched", "minor_diff", "major_diff", "missing_db_data",
                "missing_reference_data", "placeholder_reference")
        out = {k: 0 for k in keys}
        for r in self.results:
            out[r.validation_status] = out.get(r.validation_status, 0) + 1
        return out


def _pct(db: float, ref: float) -> float | None:
    return round((db - ref) / ref * 100.0, 3) if ref else None


def _classify(diffs: list[float]) -> str:
    worst = max(abs(d) for d in diffs)
    if worst <= MINOR_DIFF_PCT:
        return "matched"
    if worst <= MAJOR_DIFF_PCT:
        return "minor_diff"
    return "major_diff"


def _is_placeholder(ref: dict) -> bool:
    """레퍼런스가 placeholder인가(실제 값 아님)."""
    note = str(ref.get("source_url_or_note", "")).lower()
    if "placeholder" in note:
        return True
    vals = [ref.get("reference_close"), ref.get("high_52w"), ref.get("low_52w")]
    return any(v in (None, 0, 0.0) for v in vals)


class LeaderTrendValidationService:
    """non-KIS 레퍼런스와 DB 52주 값을 비교하는 읽기 전용 서비스.

    **DB write 0 · 외부 호출 0 · KIS 0 · SignalLog/Trade/Order/CandidateEvent 0 · 스케줄러 0.**
    """

    def __init__(
        self,
        session: AsyncSession,
        reference: dict | None = None,
        reference_path: Path | None = None,
    ) -> None:
        self._session = session
        if reference is not None:
            self._reference = reference
        else:
            path = reference_path or _DEFAULT_REFERENCE_PATH
            self._reference = json.loads(Path(path).read_text(encoding="utf-8"))

    async def _db_52w(self, symbol: str) -> tuple[float, float, float] | None:
        """(close, high_52w, low_52w) — 행 없으면 None. read-only."""
        rows = list((await self._session.execute(
            select(MarketData.high, MarketData.low, MarketData.close, MarketData.ts)
            .where(MarketData.symbol_code == symbol, MarketData.timeframe == DAILY_TIMEFRAME)
            .order_by(MarketData.ts.asc())
        )).all())
        if not rows:
            return None
        highs = [float(r[0]) for r in rows]
        lows = [float(r[1]) for r in rows]
        latest_close = float(rows[-1][2])
        return latest_close, max(highs), min(lows)

    async def validate(self, symbols: list[str] | None = None) -> ValidationReport:
        universe = symbols if symbols else list(PILOT_SYMBOLS)
        universe = universe[:MAX_SCAN_SYMBOLS]  # 최대 5(방어)
        ref_by_symbol = {s["symbol"]: s for s in self._reference.get("symbols", [])}
        report = ValidationReport(
            universe_scope="pilot_5" if not symbols else "explicit",
            symbols=universe,
            source_name=self._reference.get("source_name"),
            source_note=self._reference.get("source_note"),
            as_of_date=self._reference.get("as_of_date"),
        )
        for sym in universe:
            db = await self._db_52w(sym)
            ref = ref_by_symbol.get(sym)
            if db is None:
                report.results.append(SymbolValidation(sym, "missing_db_data",
                                                        note="no market_data 1d rows"))
                continue
            db_close, db_hi, db_lo = db
            base = SymbolValidation(
                sym, "matched", db_reference_close=round(db_close, 2),
                db_high_52w=round(db_hi, 2), db_low_52w=round(db_lo, 2),
            )
            if ref is None:
                base.validation_status = "missing_reference_data"
                base.note = "no reference entry for symbol"
                report.results.append(base); continue
            if _is_placeholder(ref):
                base.validation_status = "placeholder_reference"
                base.note = "reference is placeholder — fill non-KIS values to validate"
                report.results.append(base); continue
            r_close = float(ref["reference_close"]); r_hi = float(ref["high_52w"]); r_lo = float(ref["low_52w"])
            base.reference_close = r_close; base.reference_high_52w = r_hi; base.reference_low_52w = r_lo
            base.reference_close_diff_pct = _pct(db_close, r_close)
            base.high_52w_diff_pct = _pct(db_hi, r_hi)
            base.low_52w_diff_pct = _pct(db_lo, r_lo)
            diffs = [d for d in (base.reference_close_diff_pct, base.high_52w_diff_pct,
                                 base.low_52w_diff_pct) if d is not None]
            base.validation_status = _classify(diffs) if diffs else "missing_reference_data"
            report.results.append(base)
        return report


# --- M2.15F-3A: DB-side 52주 snapshot export(읽기 전용 · 매수 신호 아님) ---
@dataclass
class DbSnapshotRow:
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
    data_quality_note: str = "computed_from_existing_market_data_only"

    def to_dict(self) -> dict:
        return {**self.__dict__}


@dataclass
class DbSnapshotReport:
    universe_scope: str
    timeframe: str
    results: list[DbSnapshotRow] = field(default_factory=list)


def _kst_date(ts) -> str:
    return ts.astimezone(KST).strftime("%Y%m%d")


async def db_52w_snapshot(
    session: AsyncSession, symbols: list[str] | None = None
) -> DbSnapshotReport:
    """기존 market_data(1d)에서 pilot 종목별 52주 기준값을 read-only로 export.

    **DB write 0 · 외부/KIS 호출 0 · SignalLog/Trade/Order/CandidateEvent 0.** 매수 신호가 아니라
    사람이 non-KIS 레퍼런스를 채울 때 참고하는 local DB 기준값이다.
    """
    universe = (symbols if symbols else list(PILOT_SYMBOLS))[:MAX_SCAN_SYMBOLS]
    report = DbSnapshotReport(
        universe_scope="pilot_5" if not symbols else "explicit", timeframe=DAILY_TIMEFRAME
    )
    for sym in universe:
        rows = list((await session.execute(
            select(MarketData)
            .where(MarketData.symbol_code == sym, MarketData.timeframe == DAILY_TIMEFRAME)
            .order_by(MarketData.ts.asc())
        )).scalars().all())
        if not rows:
            report.results.append(DbSnapshotRow(
                symbol=sym, row_count=0, candidate_bucket_if_any=None,
                data_quality_note="missing_db_data"))
            continue
        highs = [(float(r.high), r.ts) for r in rows]
        lows = [(float(r.low), r.ts) for r in rows]
        hi_val, hi_ts = max(highs, key=lambda x: x[0])
        lo_val, lo_ts = min(lows, key=lambda x: x[0])
        last = rows[-1]
        close = float(last.close)
        m = compute_metrics(sym, rows)  # 동일 공식으로 운영 bucket 산출(매수 신호 아님)
        report.results.append(DbSnapshotRow(
            symbol=sym, row_count=len(rows),
            first_date=_kst_date(rows[0].ts), last_date=_kst_date(last.ts),
            db_reference_close=round(close, 2), db_reference_close_date=_kst_date(last.ts),
            db_high_52w=round(hi_val, 2), db_high_52w_date=_kst_date(hi_ts),
            db_low_52w=round(lo_val, 2), db_low_52w_date=_kst_date(lo_ts),
            low_52w_gain_pct=round((close / lo_val - 1) * 100, 2) if lo_val else None,
            drawdown_from_52w_high_pct=round((hi_val - close) / hi_val * 100, 2) if hi_val else None,
            candidate_bucket_if_any=m.candidate_bucket_operational,
        ))
    return report
