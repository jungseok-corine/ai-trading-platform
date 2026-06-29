"""Daily candle collector (M2.15B-2) — read-only 시세 수집 + 멱등 upsert.

주도주 추세추종(M2.15)의 52주 분석에 필요한 **일봉**을 KIS read-only 경로로 모아 `market_data`에
`timeframe="1d"`로 적재한다. **주문/거래 무관 · SignalLog/Trade/Order 미생성 · 스케줄러 없음.**
기본 dry-run(무쓰기·무 KIS 호출). execute는 호출자가 명시 confirm을 전달할 때만(스크립트 가드 + 이 단계
테스트 전용 — dev DB 미실행).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.models.market_data import MarketData
from app.domain.models.watchlist import WatchlistSymbol
from app.domain.repositories.market_data import MarketDataRepository

DAILY_TIMEFRAME = "1d"
MAX_DAILY_COUNT = 1000
DEFAULT_PILOT = ["005930", "000660"]
COVERAGE_THRESHOLDS = (20, 50, 120, 252)

# 시크릿이 메시지에 새지 않도록(헤더 기반이라 보통 없지만 방어적).
_SECRET_RE = re.compile(
    r"(api_key|appkey|appsecret|authorization|access_token|token)=?\s*[:=]?\s*[^&\s\"']+",
    re.IGNORECASE,
)


def sanitize(text: str) -> str:
    return _SECRET_RE.sub(r"\1=***REDACTED***", text)


def _ts_from_business_date(yyyymmdd: str) -> datetime:
    """KIS 거래일(YYYYMMDD)을 KST 자정 tz-aware datetime으로(거래일 canonical ts)."""
    d = datetime.strptime(yyyymmdd, "%Y%m%d")
    return d.replace(tzinfo=KST)


@dataclass
class SymbolResult:
    symbol_code: str
    status: str  # success | skipped_fresh | conflict | failed_transient | failed_permanent | insufficient_data
    fetched: int = 0
    inserted: int = 0
    conflicts: int = 0
    reason: str | None = None


@dataclass
class CollectReport:
    mode: str  # dry_run | execute
    symbols: list[str]
    count: int
    estimated_requests: int = 0
    writes: int = 0
    per_symbol: list[SymbolResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "symbols": self.symbols,
            "count": self.count,
            "estimated_requests": self.estimated_requests,
            "writes": self.writes,
            "signals_created": 0,
            "trades_created": 0,
            "orders_created": 0,
            "per_symbol": [s.__dict__ for s in self.per_symbol],
            "warnings": self.warnings,
        }


class MarketDataDailyCollector:
    """일봉 수집 서비스. provider는 `get_daily_candles(symbol, count=...)`를 가진 read-only 객체(duck-typed)."""

    def __init__(self, session: AsyncSession, daily_provider=None) -> None:
        self._session = session
        self._repo = MarketDataRepository(session)
        self._provider = daily_provider  # None이면 dry-run/coverage만 가능(KIS 미주입).

    async def build_pilot_universe(
        self, symbols: list[str] | None = None, limit: int = 5, from_watchlist: bool = False
    ) -> list[str]:
        if symbols:
            return [s.strip() for s in symbols if s.strip()]
        if from_watchlist:
            rows = (
                await self._session.execute(
                    select(WatchlistSymbol.symbol_code)
                    .distinct()
                    .order_by(WatchlistSymbol.symbol_code.asc())
                    .limit(max(1, limit))
                )
            ).scalars().all()
            return list(rows)
        return DEFAULT_PILOT[: max(1, limit)]

    def dry_run_plan(self, symbols: list[str], count: int) -> CollectReport:
        """무쓰기·무 KIS 호출 계획. 예상 요청 수만 계산(일봉 1회 ~100건 가정)."""
        per_call = 100
        est = sum(max(1, (count + per_call - 1) // per_call) for _ in symbols)
        return CollectReport(
            mode="dry_run", symbols=symbols, count=count, estimated_requests=est, writes=0,
            warnings=[
                "DRY-RUN: no DB writes, no live KIS call.",
                "No SignalLog/Trade/Order. Read-only daily market data only.",
                "execute requires explicit --execute --confirm-daily-candle-collection.",
            ],
        )

    async def coverage_report(self, symbols: list[str] | None = None) -> dict:
        """종목별 일봉(timeframe=1d) 보유 수 + 20/50/120/252 충족. 읽기 전용."""
        stmt = select(MarketData.symbol_code).where(MarketData.timeframe == DAILY_TIMEFRAME)
        if symbols:
            stmt = stmt.where(MarketData.symbol_code.in_(symbols))
        rows = (await self._session.execute(stmt)).scalars().all()
        counts: dict[str, int] = {}
        for sc in rows:
            counts[sc] = counts.get(sc, 0) + 1
        out_symbols = symbols if symbols else sorted(counts.keys())
        per = []
        for sc in out_symbols:
            n = counts.get(sc, 0)
            per.append({
                "symbol_code": sc, "daily_candles": n,
                **{f"has_{t}": n >= t for t in COVERAGE_THRESHOLDS},
                "ready_for_52w": n >= 252,
            })
        return {
            "timeframe": DAILY_TIMEFRAME,
            "symbols_with_daily": len(counts),
            "any_ready_for_52w": any(n >= 252 for n in counts.values()),
            "per_symbol": per,
        }

    async def collect(
        self, symbols: list[str], count: int = 252, *, execute: bool = False,
        overwrite: bool = False,
    ) -> CollectReport:
        """일봉 수집. execute=False면 dry-run 계획만(KIS/DB 미접촉).

        execute=True는 provider 주입 + 호출자 confirm 전제. **이 단계에서 dev DB 대상으로 실행하지 않는다**
        (스크립트 가드로 차단; 테스트 DB에서만 검증).
        """
        if not execute:
            return self.dry_run_plan(symbols, count)
        if self._provider is None:
            raise ValueError("execute requires a daily_provider (read-only KIS client)")

        report = CollectReport(mode="execute", symbols=symbols, count=count)
        for sc in symbols:
            res = await self._collect_one(sc, count, overwrite=overwrite)
            report.per_symbol.append(res)
            report.writes += res.inserted
        if report.writes:
            await self._session.flush()
        return report

    async def _collect_one(self, symbol_code: str, count: int, *, overwrite: bool) -> SymbolResult:
        try:
            candles = await self._provider.get_daily_candles(symbol_code, count=count)
        except Exception as exc:  # noqa: BLE001 - provider 장애를 종목 단위로 흡수(전체 중단 안 함)
            msg = sanitize(f"{type(exc).__name__}: {exc}")
            transient = any(k in msg.lower() for k in ("timeout", "rate", "egw00201", "503", "502", "500", "429"))
            return SymbolResult(symbol_code, "failed_transient" if transient else "failed_permanent",
                                reason=msg)
        if not candles:
            return SymbolResult(symbol_code, "insufficient_data", fetched=0,
                                reason="provider returned no daily candles")

        # 기존 일봉(timeframe=1d) 로드 → 보존/충돌 판단(인트라데이 행은 절대 건드리지 않음).
        existing = {
            row.ts: row
            for row in (
                await self._session.execute(
                    select(MarketData).where(
                        MarketData.symbol_code == symbol_code,
                        MarketData.timeframe == DAILY_TIMEFRAME,
                    )
                )
            ).scalars().all()
        }
        rows_to_upsert: list[dict] = []
        conflicts = 0
        for c in candles:
            ts = _ts_from_business_date(c.business_date)
            cur = existing.get(ts)
            new = {
                "symbol_code": symbol_code, "timeframe": DAILY_TIMEFRAME, "ts": ts,
                "open": c.open_price, "high": c.high_price, "low": c.low_price,
                "close": c.close_price, "volume": c.volume,
            }
            if cur is None:
                rows_to_upsert.append(new)
            elif (cur.open, cur.high, cur.low, cur.close, cur.volume) == (
                c.open_price, c.high_price, c.low_price, c.close_price, c.volume
            ):
                continue  # 동일값 → skip(멱등)
            else:
                conflicts += 1
                if overwrite:
                    rows_to_upsert.append(new)  # 명시 허용 시에만 갱신

        inserted = await self._repo.upsert_bulk(rows_to_upsert) if rows_to_upsert else 0
        if conflicts and not overwrite and inserted == 0:
            return SymbolResult(symbol_code, "conflict", fetched=len(candles), conflicts=conflicts,
                                reason="existing daily rows differ; not overwritten (overwrite=False)")
        if inserted == 0 and conflicts == 0:
            return SymbolResult(symbol_code, "skipped_fresh", fetched=len(candles),
                                reason="all candles already present (idempotent)")
        return SymbolResult(symbol_code, "success", fetched=len(candles), inserted=inserted,
                            conflicts=conflicts)
