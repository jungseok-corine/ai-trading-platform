"""C-6.2: 이벤트 알림 배선 — pending 제안 생성 시 즉시 알림.

안전 검증: 기본 config에서 완전 no-op (notification_events_enabled=False,
provider=none 이중 게이트).
"""
import pytest

from app.core.config import Settings, get_settings
from app.services.notifications.base import NotificationResult
from app.services.notifications.events import notify_event, notify_proposals_created


def test_default_config_events_disabled():
    """안전 불변식: 이벤트 알림은 코드 기본값에서 꺼져 있다."""
    s = Settings(_env_file=None)
    assert s.notification_events_enabled is False
    assert s.notification_provider == "none"


@pytest.mark.asyncio
async def test_notify_event_noop_when_disabled():
    """게이트 꺼짐(기본)이면 채널 생성조차 하지 않고 None."""
    result = await notify_event("제목", "본문")
    assert result is None


@pytest.mark.asyncio
async def test_notify_proposals_created_zero_count_noop(monkeypatch):
    """count<=0이면 게이트가 켜져 있어도 no-op."""
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(_env_file=None, notification_events_enabled=True),
    )
    assert await notify_proposals_created("테스트", 0) is None
    assert await notify_proposals_created("테스트", -1) is None


@pytest.mark.asyncio
async def test_notify_event_sends_via_channel_when_enabled(monkeypatch):
    """게이트 켜짐 + 채널 구성 시 채널로 전송한다."""
    sent: list[tuple[str, str]] = []

    class FakeChannel:
        async def send(self, subject: str, body: str) -> NotificationResult:
            sent.append((subject, body))
            return NotificationResult(provider="fake", sent=True)

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(_env_file=None, notification_events_enabled=True),
    )
    monkeypatch.setattr(
        "app.services.notifications.events.get_notification_channel",
        lambda provider=None: FakeChannel(),
    )

    result = await notify_proposals_created("일일 AI 분석", 3)
    assert result is not None and result.sent is True
    assert len(sent) == 1
    assert "3건" in sent[0][1]
    assert "승인 전에는" in sent[0][1]


@pytest.mark.asyncio
async def test_notify_event_swallows_channel_errors(monkeypatch):
    """채널 예외는 삼키고 sent=False 결과를 반환한다 (잡 중단 방지)."""

    def _boom(provider=None):
        raise RuntimeError("channel down")

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(_env_file=None, notification_events_enabled=True),
    )
    monkeypatch.setattr(
        "app.services.notifications.events.get_notification_channel", _boom
    )

    result = await notify_event("제목", "본문")
    assert result is not None
    assert result.sent is False
    assert "channel down" in (result.reason or "")


def test_get_settings_cache_not_polluted():
    """monkeypatch 이후 실제 get_settings 기본값이 오염되지 않았는지 확인."""
    get_settings.cache_clear()
    assert get_settings().notification_events_enabled is False
