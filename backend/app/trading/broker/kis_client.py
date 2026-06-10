import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from app.trading.broker.exceptions import KISAPIError

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

# 토큰 만료 전 미리 갱신하기 위한 여유 시간
TOKEN_REFRESH_BUFFER = timedelta(minutes=5)


class KISClientBase:
    """KIS Open API 공통 클라이언트.

    접근 토큰 발급/캐싱/자동 갱신과 공통 요청 헤더 처리를 담당한다.
    실전/모의투자 구현체(KISPaperBrokerClient, KISRealBrokerClient)는
    이 클래스를 상속해 base_url과 tr_id만 다르게 사용한다.
    """

    def __init__(
        self,
        *,
        base_url: str,
        app_key: str,
        app_secret: str,
        http_client: httpx.AsyncClient,
        token_cache_path: str | Path,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._app_key = app_key
        self._app_secret = app_secret
        self._http = http_client
        self._token_cache_path = Path(token_cache_path)
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None
        self._token_lock = asyncio.Lock()

    async def _get_access_token(self) -> str:
        async with self._token_lock:
            if self._is_token_valid(self._access_token, self._token_expires_at):
                return self._access_token  # type: ignore[return-value]

            cached = self._load_cached_token()
            if cached and self._is_token_valid(*cached):
                self._access_token, self._token_expires_at = cached
                return self._access_token

            await self._issue_token()
            return self._access_token  # type: ignore[return-value]

    @staticmethod
    def _is_token_valid(token: str | None, expires_at: datetime | None) -> bool:
        if token is None or expires_at is None:
            return False
        return datetime.now(KST) < expires_at - TOKEN_REFRESH_BUFFER

    async def _issue_token(self) -> None:
        response = await self._http.post(
            f"{self._base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
            },
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        if response.status_code != 200:
            body = response.json()
            raise KISAPIError(
                body.get("error_code", str(response.status_code)),
                body.get("error_description", response.text),
            )
        data = response.json()

        self._access_token = data["access_token"]
        self._token_expires_at = datetime.strptime(
            data["access_token_token_expired"], "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=KST)
        self._save_cached_token()
        logger.info("Issued new KIS access token, expires at %s", self._token_expires_at)

    def _load_cached_token(self) -> tuple[str, datetime] | None:
        if not self._token_cache_path.exists():
            return None
        try:
            data = json.loads(self._token_cache_path.read_text())
            return data["access_token"], datetime.fromisoformat(data["expires_at"])
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def _save_cached_token(self) -> None:
        self._token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_cache_path.write_text(
            json.dumps(
                {
                    "access_token": self._access_token,
                    "expires_at": self._token_expires_at.isoformat(),  # type: ignore[union-attr]
                }
            )
        )

    async def _request(
        self,
        method: str,
        path: str,
        tr_id: str,
        params: dict[str, str] | None = None,
    ) -> dict:
        token = await self._get_access_token()
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        response = await self._http.request(
            method, f"{self._base_url}{path}", headers=headers, params=params
        )
        if response.status_code != 200:
            raise KISAPIError(str(response.status_code), response.text)
        data = response.json()

        if data.get("rt_cd") != "0":
            raise KISAPIError(data.get("msg_cd", ""), data.get("msg1", ""))

        return data
