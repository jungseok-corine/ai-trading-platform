from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.market_context import MarketContextSnapshot
from app.domain.models.market_data import MarketData
from app.domain.repositories.candidate_event import CandidateEventRepository


@dataclass
class _Bucket:
    count: int = 0
    wins: int = 0
    return_sum: Decimal = Decimal("0")

    def add(self, ret: Decimal) -> None:
        self.count += 1
        if ret > 0:
            self.wins += 1
        self.return_sum += ret

    def to_dict(self) -> dict:
        if self.count == 0:
            return {"count": 0, "win_rate": None, "avg_return_pct": None}
        return {
            "count": self.count,
            "win_rate": round(self.wins / self.count * 100, 2),
            "avg_return_pct": float((self.return_sum / self.count).quantize(Decimal("0.0001"))),
        }


@dataclass
class CandidateAnalysis:
    horizon_minutes: int
    total: int
    analyzed: int
    overall: dict
    by_time_bucket: dict = field(default_factory=dict)
    by_condition: dict = field(default_factory=dict)


class CandidateOutcomeService:
    """후보 발견 이후의 forward 수익률을 계산해 스캐너 조건·시간대별 성과를 집계한다 (C-2.38).

    "이 조건이 실제로 성과에 도움이 되는가?"(문서 6.2)에 답하기 위한 기반.
    수익률 = (triggered_at+horizon 종가 − triggered_at 종가) / triggered_at 종가.
    market_data가 부족한 후보는 분석에서 제외한다(주문/체결과 무관, read-only 집계).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._candidate_repo = CandidateEventRepository(session)

    async def _close_at_or_before(
        self, symbol_code: str, timeframe: str, ts: datetime
    ) -> Decimal | None:
        result = await self._session.execute(
            select(MarketData.close)
            .where(
                MarketData.symbol_code == symbol_code,
                MarketData.timeframe == timeframe,
                MarketData.ts <= ts,
            )
            .order_by(MarketData.ts.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _time_bucket_map(self, snapshot_ids: set[int]) -> dict[int, str | None]:
        if not snapshot_ids:
            return {}
        result = await self._session.execute(
            select(MarketContextSnapshot.id, MarketContextSnapshot.time_bucket).where(
                MarketContextSnapshot.id.in_(snapshot_ids)
            )
        )
        return {row[0]: row[1] for row in result.all()}

    async def analyze(
        self,
        scanner_rule_version_id: int | None = None,
        horizon_minutes: int = 30,
        timeframe: str = "1m",
        limit: int = 500,
    ) -> CandidateAnalysis:
        candidates = await self._candidate_repo.list_filtered(
            scanner_rule_version_id=scanner_rule_version_id, limit=limit
        )
        snapshot_ids = {c.context_snapshot_id for c in candidates if c.context_snapshot_id}
        bucket_map = await self._time_bucket_map(snapshot_ids)

        overall = _Bucket()
        by_time_bucket: dict[str, _Bucket] = defaultdict(_Bucket)
        by_condition: dict[str, _Bucket] = defaultdict(_Bucket)
        analyzed = 0

        for c in candidates:
            entry = await self._close_at_or_before(c.symbol_code, timeframe, c.triggered_at)
            exit_close = await self._close_at_or_before(
                c.symbol_code, timeframe, c.triggered_at + timedelta(minutes=horizon_minutes)
            )
            if entry is None or exit_close is None or entry == 0:
                continue
            ret = (exit_close - entry) / entry * 100
            analyzed += 1
            overall.add(ret)

            bucket = bucket_map.get(c.context_snapshot_id) if c.context_snapshot_id else None
            if bucket:
                by_time_bucket[bucket].add(ret)
            for cond in c.matched_conditions or []:
                by_condition[cond].add(ret)

        return CandidateAnalysis(
            horizon_minutes=horizon_minutes,
            total=len(candidates),
            analyzed=analyzed,
            overall=overall.to_dict(),
            by_time_bucket={k: v.to_dict() for k, v in by_time_bucket.items()},
            by_condition={k: v.to_dict() for k, v in by_condition.items()},
        )
