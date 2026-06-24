"""Action Inbox API (v1) — 검토 대기 항목의 read-only 집계.

`GET /action-inbox` — 검토가 필요한 항목 목록(읽기 전용). 승인/거절·잡 토글·실거래 동작 없음.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.action_inbox_service import ActionInboxService

router = APIRouter(prefix="/action-inbox", tags=["action-inbox"])


def get_service(session: AsyncSession = Depends(get_db)) -> ActionInboxService:
    return ActionInboxService(session)


@router.get("")
async def get_action_inbox(
    service: ActionInboxService = Depends(get_service),
) -> dict:
    return await service.items()
