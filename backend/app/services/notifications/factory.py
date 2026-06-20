from __future__ import annotations

from app.services.notifications.base import NotificationChannel
from app.services.notifications.channels import LogChannel, NoneChannel

# 등록된 채널. 외부 전송 채널(telegram 등)은 키가 준비되면 여기 추가한다.
_CHANNELS = {
    "none": NoneChannel,
    "log": LogChannel,
}


def get_notification_channel(provider: str | None = None) -> NotificationChannel:
    """provider 이름으로 알림 채널을 만든다. 미지정/미등록이면 안전 기본값 none."""
    cls = _CHANNELS.get((provider or "none").lower(), NoneChannel)
    return cls()
