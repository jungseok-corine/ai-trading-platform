"""인트라데이 변동성 레짐 분류 (C-6.3, 5m 병용 C-6.15).

저장된 분봉(market_data 1m/5m — 심볼별 커버리지 좋은 쪽)으로
"지금 시장이 평소보다 얼마나 요동치는가"를 분류한다.

방법:
- 심볼별 True Range%((high-low)/close)의 최근 N봉 평균을 장기 기준선 평균과 비교(ratio)
- 심볼들의 ratio 중앙값으로 시장 레짐 결정:
  calm(< calm_ratio) / normal / elevated(>= elevated_ratio) / extreme(>= extreme_ratio)
- 데이터 부족(심볼 min_symbols 미만)이면 unknown — 소비자는 normal처럼 취급해야 한다
  (unknown이 매매를 막지 않는다).

안전 경계: DB read-only 계산. 주문/브로커/KIS/LLM 호출 없음.
레짐은 판단 재료일 뿐 — 이 서비스 자체는 아무것도 실행하지 않는다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.market_data import MarketData

REGIME_CALM = "calm"
REGIME_NORMAL = "normal"
REGIME_ELEVATED = "elevated"
REGIME_EXTREME = "extreme"
REGIME_UNKNOWN = "unknown"

# 레짐 판단에 쓸 심볼 수 상한 (스냅샷당 심볼별 쿼리 1회씩이라 제한)
MAX_SYMBOLS = 20

# 레짐 계산에 쓰는 timeframe과 분 단위 스케일 (C-6.15: 유니버스 전략이 5m 위주라 병용).
TIMEFRAME_SCALE = {"1m": 1, "5m": 5}


@dataclass
class RegimeSnapshot:
    market: str
    regime: str
    vol_ratio: float | None
    symbols_used: int
    as_of: datetime
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "regime": self.regime,
            "vol_ratio": self.vol_ratio,
            "symbols_used": self.symbols_used,
            "as_of": self.as_of.isoformat(),
            "detail": self.detail,
        }


# 프로세스 내 짧은 TTL 캐시 — 러너가 tick마다 불러도 DB를 두들기지 않게.
_cache: dict[str, tuple[float, RegimeSnapshot]] = {}


class IntradayRegimeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = get_settings()

    async def snapshot(
        self,
        market: str = "KR",
        *,
        as_of: datetime | None = None,
        symbols: list[str] | None = None,
        use_cache: bool = True,
    ) -> RegimeSnapshot:
        """현재 변동성 레짐 스냅샷. as_of/symbols는 테스트·재현용 주입 지점."""
        s = self._settings
        cache_key = market
        injected = as_of is not None or symbols is not None
        if use_cache and not injected:
            hit = _cache.get(cache_key)
            if hit is not None and time.monotonic() - hit[0] < s.intraday_regime_cache_seconds:
                return hit[1]

        now = as_of or datetime.now(timezone.utc)
        # 심볼별 최적 timeframe(1m 우선, 부족하면 5m) 해석 — 유니버스 전략이 5m 위주라
        # 1m만 보면 표본이 부족해 unknown이 되던 문제(C-6.15) 해소.
        if symbols is None:
            targets = await self._active_symbols(now)
        else:
            targets = await self._resolve_timeframes(symbols, now)

        ratios: dict[str, float] = {}
        timeframes: dict[str, str] = {}
        for symbol, timeframe in targets[:MAX_SYMBOLS]:
            ratio = await self._symbol_vol_ratio(symbol, timeframe, now)
            if ratio is not None:
                ratios[symbol] = ratio
                timeframes[symbol] = timeframe

        if len(ratios) < s.intraday_regime_min_symbols:
            snap = RegimeSnapshot(
                market=market,
                regime=REGIME_UNKNOWN,
                vol_ratio=None,
                symbols_used=len(ratios),
                as_of=now,
                detail={"reason": f"데이터 심볼 부족 ({len(ratios)} < {s.intraday_regime_min_symbols})"},
            )
        else:
            agg = float(median(ratios.values()))
            snap = RegimeSnapshot(
                market=market,
                regime=self._classify(agg),
                vol_ratio=round(agg, 4),
                symbols_used=len(ratios),
                as_of=now,
                detail={
                    "per_symbol_ratio": {k: round(v, 4) for k, v in sorted(ratios.items())},
                    "per_symbol_timeframe": dict(sorted(timeframes.items())),
                    "thresholds": {
                        "calm": s.intraday_regime_calm_ratio,
                        "elevated": s.intraday_regime_elevated_ratio,
                        "extreme": s.intraday_regime_extreme_ratio,
                    },
                },
            )

        if use_cache and not injected:
            _cache[cache_key] = (time.monotonic(), snap)
        return snap

    def _classify(self, ratio: float) -> str:
        s = self._settings
        if ratio >= s.intraday_regime_extreme_ratio:
            return REGIME_EXTREME
        if ratio >= s.intraday_regime_elevated_ratio:
            return REGIME_ELEVATED
        if ratio < s.intraday_regime_calm_ratio:
            return REGIME_CALM
        return REGIME_NORMAL

    async def _recent_coverage(
        self, as_of: datetime, symbols: list[str] | None = None
    ) -> list[tuple[str, str]]:
        """최근 2일 내 (심볼, timeframe)별 봉 수 → 심볼당 최적 timeframe 선택.

        선택 규칙: 분 단위 커버리지(봉수×스케일)가 큰 쪽. 동률이면 해상도 높은 1m.
        반환은 커버리지 큰 심볼 순.
        """
        stmt = (
            select(MarketData.symbol_code, MarketData.timeframe, func.count().label("n"))
            .where(
                MarketData.timeframe.in_(list(TIMEFRAME_SCALE)),
                MarketData.ts >= as_of - timedelta(days=2),
                MarketData.ts <= as_of,
            )
            .group_by(MarketData.symbol_code, MarketData.timeframe)
        )
        if symbols is not None:
            stmt = stmt.where(MarketData.symbol_code.in_(symbols))
        rows = (await self._session.execute(stmt)).all()

        best: dict[str, tuple[str, int]] = {}  # symbol -> (timeframe, coverage_minutes)
        for sym, tf, n in rows:
            coverage = n * TIMEFRAME_SCALE[tf]
            current = best.get(sym)
            if (
                current is None
                or coverage > current[1]
                or (coverage == current[1] and TIMEFRAME_SCALE[tf] < TIMEFRAME_SCALE[current[0]])
            ):
                best[sym] = (tf, coverage)
        ordered = sorted(best.items(), key=lambda kv: kv[1][1], reverse=True)
        return [(sym, tf) for sym, (tf, _cov) in ordered[:MAX_SYMBOLS]]

    async def _active_symbols(self, as_of: datetime) -> list[tuple[str, str]]:
        return await self._recent_coverage(as_of)

    async def _resolve_timeframes(
        self, symbols: list[str], as_of: datetime
    ) -> list[tuple[str, str]]:
        """주입된 심볼 목록의 최적 timeframe 해석 (데이터 없는 심볼은 1m로 시도)."""
        resolved = dict(await self._recent_coverage(as_of, symbols=symbols))
        return [(s, resolved.get(s, "1m")) for s in symbols]

    async def _symbol_vol_ratio(
        self, symbol: str, timeframe: str, as_of: datetime
    ) -> float | None:
        """최근 recent TR% 평균 / 기준선 baseline TR% 평균 (봉 수는 timeframe에 맞게 환산)."""
        s = self._settings
        scale = TIMEFRAME_SCALE.get(timeframe, 1)
        recent_n = max(6, s.intraday_regime_recent_bars // scale)
        baseline_n = max(recent_n * 2, s.intraday_regime_baseline_bars // scale)
        stmt = (
            select(MarketData.high, MarketData.low, MarketData.close)
            .where(
                MarketData.symbol_code == symbol,
                MarketData.timeframe == timeframe,
                MarketData.ts <= as_of,
            )
            .order_by(MarketData.ts.desc())
            .limit(baseline_n)
        )
        rows = (await self._session.execute(stmt)).all()
        # rows는 최신순 — TR% 리스트도 최신순
        trs = [
            float((high - low) / close)
            for high, low, close in rows
            if close and close > 0
        ]
        if len(trs) < recent_n * 2:
            return None  # 기준선을 만들 데이터가 부족
        recent = trs[:recent_n]
        baseline_avg = sum(trs) / len(trs)
        if baseline_avg <= 0:
            return None
        return (sum(recent) / len(recent)) / baseline_avg


def clear_regime_cache() -> None:
    """테스트용 캐시 초기화."""
    _cache.clear()
