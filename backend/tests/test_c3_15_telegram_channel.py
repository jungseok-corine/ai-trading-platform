"""C-3.15 Telegram 알림 채널 테스트 (MockTransport, 외부 네트워크 없음)."""

import httpx

from app.services.notifications.telegram import TelegramChannel


async def test_telegram_noop_without_config() -> None:
    # token/chat_id 없으면 외부 호출 없이 no-op
    r = await TelegramChannel(None, None).send("s", "b")
    assert r.sent is False and "미설정" in (r.reason or "")
    r2 = await TelegramChannel("tok", None).send("s", "b")
    assert r2.sent is False


async def test_telegram_sends_with_mock_transport() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        ch = TelegramChannel("BOTTOKEN", "12345", client=client)
        r = await ch.send("운영 다이제스트", "본문")
    assert r.sent is True and r.provider == "telegram"
    assert "/botBOTTOKEN/sendMessage" in seen["url"]
    assert "12345" in seen["body"]


async def test_telegram_handles_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        r = await TelegramChannel("BAD", "12345", client=client).send("s", "b")
    assert r.sent is False and "전송 실패" in (r.reason or "")
