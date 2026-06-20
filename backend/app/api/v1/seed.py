"""예시 시딩 API (C-2.58).

연구 루프가 바로 돌아갈 예시 스캐너 룰 + 전략 + 배정 룰을 멱등으로 생성한다.
모든 전략은 auto_trade_enabled=False·status=TESTING (실거래/자동매매 없음).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.seed_service import SeedService

router = APIRouter(prefix="/seed", tags=["seed"])


def get_service(session: AsyncSession = Depends(get_db)) -> SeedService:
    return SeedService(session)


@router.post("/examples", status_code=201)
async def seed_examples(service: SeedService = Depends(get_service)) -> dict:
    """예시 스캐너/전략/배정 룰을 시딩한다(멱등). 이미 있으면 건너뛴다."""
    summary = await service.seed_examples()
    return summary.to_dict()
