"""이벤트 알림 헬퍼 (C-6.2).

pending 제안 생성 같은 '사람 조치가 필요한 이벤트'를 설정된 채널로 즉시 알린다.

안전 경계:
- `notification_events_enabled=False`(기본)면 완전 no-op — 기존 동작 무변경.
- 채널 provider 기본값도 none(no-op)이라 이중 게이트.
- 알림 실패는 삼켜서 호출한 잡을 중단시키지 않는다 (best-effort).
"""
from __future__ import annotations

import logging

from app.services.notifications.base import NotificationResult
from app.services.notifications.factory import get_notification_channel

logger = logging.getLogger(__name__)


async def notify_event(subject: str, body: str) -> NotificationResult | None:
    """이벤트 알림을 보낸다. 게이트 꺼짐이면 None, 아니면 채널 전송 결과."""
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.notification_events_enabled:
        return None
    try:
        channel = get_notification_channel(settings.notification_provider)
        return await channel.send(subject, body)
    except Exception as exc:  # noqa: BLE001 - 알림 실패가 잡을 중단시키지 않도록
        logger.error("event notification failed: %s", exc)
        return NotificationResult(provider="error", sent=False, reason=str(exc))


async def notify_proposals_created(source: str, count: int) -> NotificationResult | None:
    """pending 제안이 생성됐을 때 검토 요청 알림. count<=0이면 no-op."""
    if count <= 0:
        return None
    return await notify_event(
        "AI 제안 검토 요청",
        f"{source}: pending 제안 {count}건 생성 — 검토가 필요합니다.\n"
        "(승인 전에는 어떤 실행/자동매매도 없습니다)",
    )
