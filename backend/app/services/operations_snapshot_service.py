from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.operations_snapshot import OperationsSnapshot
from app.services.operations_overview_service import OperationsOverviewService


class OperationsSnapshotService:
    """운영 종합 스냅샷 적재·추세 조회 (C-3.17).

    운영 종합(C-3.5)의 헤드라인을 일자별 한 행으로 upsert해 추세를 본다. 같은 날 다시
    적재하면 갱신(멱등). read-only 집계의 적재이며 주문/외부 호출이 없다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._overview = OperationsOverviewService(session)

    async def record(self, snapshot_date: date | None = None, days: int = 30) -> dict:
        snapshot_date = snapshot_date or datetime.now(timezone.utc).date()
        ov = await self._overview.overview(days=days)

        existing = (
            await self._session.execute(
                select(OperationsSnapshot).where(
                    OperationsSnapshot.snapshot_date == snapshot_date
                )
            )
        ).scalars().first()

        fields = {
            "invariants_ok": ov["safety"]["invariants_ok"],
            "pending_total": ov["research"]["pending_total"],
            "promotion_ready": ov["research"]["promotion_ready"],
            "est_cost_usd": ov["cost"]["est_cost_usd"],
            "total_pnl": ov["trading"]["total_pnl"],
            "win_rate": ov["trading"]["win_rate"],
            "data": ov,
        }
        if existing is None:
            row = OperationsSnapshot(snapshot_date=snapshot_date, **fields)
            self._session.add(row)
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
            row = existing
        await self._session.flush()
        return self._to_dict(row)

    async def trend(self, days: int = 30) -> list[dict]:
        rows = (
            await self._session.execute(
                select(OperationsSnapshot)
                .order_by(OperationsSnapshot.snapshot_date.desc())
                .limit(days)
            )
        ).scalars().all()
        return [self._to_dict(r) for r in reversed(rows)]

    @staticmethod
    def _to_dict(r: OperationsSnapshot) -> dict:
        return {
            "snapshot_date": r.snapshot_date.isoformat(),
            "invariants_ok": r.invariants_ok,
            "pending_total": r.pending_total,
            "promotion_ready": r.promotion_ready,
            "est_cost_usd": r.est_cost_usd,
            "total_pnl": r.total_pnl,
            "win_rate": r.win_rate,
        }
