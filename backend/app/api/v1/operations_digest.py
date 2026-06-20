"""운영 다이제스트 API (C-3.8).

`GET /operations-digest` — 조치가 필요한 항목만 추린 다이제스트(미리보기, 전송 없음).
`POST /operations-digest/notify` — 설정된 알림 채널로 전송. 기본 채널은 none(no-op)이라
기본 상태에선 외부로 아무것도 보내지 않는다(안전).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.services.notifications import get_notification_channel
from app.services.operations_digest_service import OperationsDigestService

router = APIRouter(prefix="/operations-digest", tags=["operations-digest"])


def get_service(session: AsyncSession = Depends(get_db)) -> OperationsDigestService:
    return OperationsDigestService(session)


@router.get("")
async def get_digest(
    days: int = Query(30, ge=1, le=365),
    service: OperationsDigestService = Depends(get_service),
) -> dict:
    return await service.build(days=days)


@router.post("/notify")
async def notify(
    days: int = Query(30, ge=1, le=365),
    only_if_alerts: bool = Query(True),
    service: OperationsDigestService = Depends(get_service),
) -> dict:
    """다이제스트를 설정된 채널로 보낸다. 기본 채널 none이면 전송하지 않는다.

    only_if_alerts=True(기본)면 조치 항목이 없을 때 전송을 건너뛴다.
    """
    digest = await service.build(days=days)
    channel = get_notification_channel(get_settings().notification_provider)
    if only_if_alerts and not digest["has_alerts"]:
        result = {"provider": channel.name, "sent": False, "reason": "조치 항목 없음(skip)"}
    else:
        body = service.render_text(digest)
        result = (await channel.send("운영 다이제스트", body)).to_dict()
    return {"digest": digest, "notification": result}
