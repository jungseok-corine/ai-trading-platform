import asyncio
import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from app.trading.broker.error_classifier import KIS_ERROR_RATE_LIMIT, classify_kis_error
from app.trading.broker.exceptions import KISAPIError
from app.trading.broker.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

# 토큰 만료 전 미리 갱신하기 위한 여유 시간
TOKEN_REFRESH_BUFFER = timedelta(minutes=5)


def _is_retryable_exception(exc: Exception) -> bool:
    """일시적 네트워크/서버 오류 및 EGW00201(호출 제한)이면 재시도 대상으로 판단한다.

    주문 API(place_order)는 중복주문 위험이 있으므로 retryable=False로 호출해야 한다.
    토큰 오류·잔고 부족·호가단위 오류 등은 재시도해도 해소되지 않으므로 제외한다.
    """
    if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, KISAPIError) and classify_kis_error(exc) == KIS_ERROR_RATE_LIMIT:
        return True
    return False


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
        rate_limit_min_interval_seconds: float = 0.5,
        rate_limit_cooldown_seconds: float = 7.0,
        request_max_retries: int = 2,
        request_retry_base_delay_seconds: float = 1.0,
        request_retry_max_delay_seconds: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._app_key = app_key
        self._app_secret = app_secret
        self._http = http_client
        self._token_cache_path = Path(token_cache_path)
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None
        self._token_lock = asyncio.Lock()
        self._rate_limiter = RateLimiter(
            min_interval_seconds=rate_limit_min_interval_seconds,
            cooldown_seconds=rate_limit_cooldown_seconds,
        )
        self._max_retries = request_max_retries
        self._retry_base_delay = request_retry_base_delay_seconds
        self._retry_max_delay = request_retry_max_delay_seconds

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
        await self._rate_limiter.acquire()
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
            error = KISAPIError(
                body.get("error_code", str(response.status_code)),
                body.get("error_description", response.text),
            )
            if classify_kis_error(error) == KIS_ERROR_RATE_LIMIT:
                self._rate_limiter.trigger_cooldown()
            raise error
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
        json_body: dict | None = None,
        retryable: bool = True,
    ) -> dict:
        """KIS API에 단일 요청을 보내고 응답 dict를 반환한다.

        retryable=True(기본값)이면 일시적 오류(ReadTimeout, RemoteProtocolError,
        EGW00201) 발생 시 exponential backoff + jitter로 최대 max_retries번 재시도한다.
        retryable=False이면 즉시 raise한다 — place_order처럼 중복 실행이 위험한 경우.
        """
        max_attempts = (self._max_retries + 1) if retryable else 1

        for attempt in range(max_attempts):
            if attempt > 0:
                raw_delay = min(
                    self._retry_base_delay * (2 ** (attempt - 1)),
                    self._retry_max_delay,
                )
                jitter = random.uniform(-raw_delay * 0.2, raw_delay * 0.2)
                delay = max(0.0, raw_delay + jitter)
                logger.info(
                    "KIS request retry %d/%d for %s %s after %.2fs delay",
                    attempt, self._max_retries, method, path, delay,
                )
                await asyncio.sleep(delay)

            try:
                token = await self._get_access_token()
                headers = {
                    "Content-Type": "application/json; charset=utf-8",
                    "authorization": f"Bearer {token}",
                    "appkey": self._app_key,
                    "appsecret": self._app_secret,
                    "tr_id": tr_id,
                    "custtype": "P",
                }
                await self._rate_limiter.acquire()
                response = await self._http.request(
                    method, f"{self._base_url}{path}", headers=headers, params=params, json=json_body
                )
                if response.status_code != 200:
                    raise KISAPIError(str(response.status_code), response.text)
                data = response.json()

                if data.get("rt_cd") != "0":
                    error = KISAPIError(data.get("msg_cd", ""), data.get("msg1", ""))
                    if classify_kis_error(error) == KIS_ERROR_RATE_LIMIT:
                        self._rate_limiter.trigger_cooldown()
                    raise error

                return data

            except Exception as exc:
                is_last_attempt = attempt == max_attempts - 1
                if not _is_retryable_exception(exc) or is_last_attempt:
                    raise
                logger.warning(
                    "KIS request failed (attempt %d/%d), will retry: %s: %s",
                    attempt + 1, max_attempts, type(exc).__name__, exc,
                )

        raise RuntimeError("unreachable")  # type checker appeasement
