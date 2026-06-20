from __future__ import annotations

from app.services.notifications.base import NotificationChannel
from app.services.notifications.channels import LogChannel, NoneChannel
from app.services.notifications.telegram import TelegramChannel


def get_notification_channel(provider: str | None = None) -> NotificationChannel:
    """provider 이름으로 알림 채널을 만든다. 미지정/미등록이면 안전 기본값 none.

    telegram은 config의 token/chat_id로 구성한다(둘 다 없으면 채널이 no-op).
    """
    name = (provider or "none").lower()
    if name == "log":
        return LogChannel()
    if name == "telegram":
        from app.core.config import get_settings

        s = get_settings()
        return TelegramChannel(
            s.telegram_bot_token, s.telegram_chat_id,
            timeout_seconds=s.notification_timeout_seconds,
        )
    return NoneChannel()
