from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class NotificationResult:
    provider: str
    sent: bool
    reason: str | None = None

    def to_dict(self) -> dict:
        return {"provider": self.provider, "sent": self.sent, "reason": self.reason}


class NotificationChannel(Protocol):
    """알림 채널 인터페이스. 외부 전송은 구현체의 책임."""

    name: str

    async def send(self, subject: str, body: str) -> NotificationResult: ...
