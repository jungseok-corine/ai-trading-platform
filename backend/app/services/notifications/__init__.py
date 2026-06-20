"""운영 알림 채널 추상화 (C-3.8).

기본은 `none`(no-op) — 외부로 아무것도 보내지 않는다. `log`는 로거에만 남긴다.
실제 외부 채널(Telegram/Slack 등)은 사용자가 토큰을 넣고 명시적으로 켤 때 붙인다
(us_market provider 패턴과 동일: 기본 비활성, 키 없으면 no-op).
"""
from app.services.notifications.base import NotificationChannel, NotificationResult
from app.services.notifications.factory import get_notification_channel

__all__ = ["NotificationChannel", "NotificationResult", "get_notification_channel"]
