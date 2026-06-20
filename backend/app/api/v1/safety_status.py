"""안전 불변식 점검 패널 API (C-3.3).

실거래 비활성/자동매매 off/가드·비상정지 상태를 한 번에 반환한다.
read-only 점검 — 아무것도 바꾸지 않고, 드리프트는 경고 문자열로만 알린다.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.safety_status_service import SafetyStatusService

router = APIRouter(prefix="/safety-status", tags=["safety-status"])


def get_service(session: AsyncSession = Depends(get_db)) -> SafetyStatusService:
    return SafetyStatusService(session)


@router.get("")
async def get_safety_status(
    service: SafetyStatusService = Depends(get_service),
) -> dict:
    return await service.status()
