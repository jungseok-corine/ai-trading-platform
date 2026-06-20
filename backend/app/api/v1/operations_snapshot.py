"""운영 종합 스냅샷 적재·추세 API (C-3.17).

`POST /operations-snapshot/record` — 오늘자 헤드라인을 적재(멱등 upsert).
`GET /operations-snapshot/trend?days=N` — 최근 N개 스냅샷 추세.
read-only 집계의 적재로 주문/외부 호출이 없다.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.operations_snapshot_service import OperationsSnapshotService

router = APIRouter(prefix="/operations-snapshot", tags=["operations-snapshot"])


def get_service(session: AsyncSession = Depends(get_db)) -> OperationsSnapshotService:
    return OperationsSnapshotService(session)


@router.post("/record")
async def record(
    service: OperationsSnapshotService = Depends(get_service),
    session: AsyncSession = Depends(get_db),
) -> dict:
    result = await service.record()
    await session.commit()
    return result


@router.get("/trend")
async def trend(
    days: int = Query(30, ge=1, le=365),
    service: OperationsSnapshotService = Depends(get_service),
) -> list[dict]:
    return await service.trend(days=days)
