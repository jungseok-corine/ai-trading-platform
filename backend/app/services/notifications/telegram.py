from __future__ import annotations

import httpx

from app.services.notifications.base import NotificationResult

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramChannel:
    """Telegram 봇으로 알림을 보내는 채널 (C-3.15).

    bot token + chat_id가 모두 설정돼야 전송한다. 둘 중 하나라도 없으면 no-op(sent=False)로
    안전하게 빠진다(키 없으면 외부 호출 자체를 안 함 — us_market provider 패턴과 동일).
    실제 전송은 사용자가 provider=telegram + 토큰/chat_id를 명시적으로 설정할 때만 일어난다.
    """

    name = "telegram"

    def __init__(
        self,
        bot_token: str | None,
        chat_id: str | None,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._timeout = timeout_seconds
        self._client = client

    async def send(self, subject: str, body: str) -> NotificationResult:
        if not self._token or not self._chat_id:
            return NotificationResult(
                provider=self.name, sent=False, reason="telegram 미설정(token/chat_id 필요)"
            )
        text = f"*{subject}*\n{body}"
        url = f"{TELEGRAM_API_BASE}/bot{self._token}/sendMessage"
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns_client = self._client is None
        try:
            resp = await client.post(
                url, json={"chat_id": self._chat_id, "text": text, "parse_mode": "Markdown"}
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return NotificationResult(provider=self.name, sent=False, reason=f"전송 실패: {e}")
        finally:
            if owns_client:
                await client.aclose()
        return NotificationResult(provider=self.name, sent=True)
