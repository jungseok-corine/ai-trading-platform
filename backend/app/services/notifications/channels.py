from __future__ import annotations

import logging

from app.services.notifications.base import NotificationResult

logger = logging.getLogger("operations.notify")


class NoneChannel:
    """기본 채널 — 외부로 아무것도 보내지 않는다(no-op). 안전 기본값."""

    name = "none"

    async def send(self, subject: str, body: str) -> NotificationResult:
        return NotificationResult(provider=self.name, sent=False, reason="채널 비활성(none)")


class LogChannel:
    """로거에만 남기는 채널 — 외부 네트워크 호출 없음."""

    name = "log"

    async def send(self, subject: str, body: str) -> NotificationResult:
        logger.info("[operations-notify] %s\n%s", subject, body)
        return NotificationResult(provider=self.name, sent=True)
