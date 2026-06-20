"""C-3.17 운영 종합 스냅샷 적재·추세 테스트."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.operations_snapshot_service import OperationsSnapshotService


async def test_record_is_idempotent_per_day(db_session: AsyncSession) -> None:
    svc = OperationsSnapshotService(db_session)
    d = date(2026, 6, 20)
    r1 = await svc.record(snapshot_date=d)
    assert r1["snapshot_date"] == "2026-06-20"
    assert r1["invariants_ok"] is True

    # 같은 날 다시 적재 → 갱신(중복 행 없음)
    await svc.record(snapshot_date=d)
    trend = await svc.trend(days=30)
    assert len([t for t in trend if t["snapshot_date"] == "2026-06-20"]) == 1


async def test_trend_orders_ascending(db_session: AsyncSession) -> None:
    svc = OperationsSnapshotService(db_session)
    await svc.record(snapshot_date=date(2026, 6, 18))
    await svc.record(snapshot_date=date(2026, 6, 19))
    await svc.record(snapshot_date=date(2026, 6, 20))
    trend = await svc.trend(days=2)
    # 최근 2개를 오래된 순으로
    assert [t["snapshot_date"] for t in trend] == ["2026-06-19", "2026-06-20"]
