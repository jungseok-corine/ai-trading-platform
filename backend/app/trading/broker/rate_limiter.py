import asyncio
import time


class RateLimiter:
    """KIS Open API 호출 빈도를 제한한다.

    모의투자(VTS) 서버는 초당 호출 건수 제한이 엄격해 짧은 간격으로 연속 호출하면
    EGW00201("초당 거래건수를 초과하였습니다")이 쉽게 발생한다. 동일 프로세스 내
    모든 KIS 요청이 이 limiter를 통과하도록 해 최소 호출 간격을 보장하고, 호출
    제한 오류가 발생했을 때는 cooldown 동안 추가 호출을 지연시킨다.
    """

    def __init__(self, min_interval_seconds: float = 0.5, cooldown_seconds: float = 7.0) -> None:
        self._min_interval = min_interval_seconds
        self._cooldown = cooldown_seconds
        self._lock = asyncio.Lock()
        self._next_allowed_at: float = 0.0

    async def acquire(self) -> None:
        """이전 호출로부터 최소 간격(또는 cooldown)이 지날 때까지 대기한다."""
        async with self._lock:
            now = time.monotonic()
            wait = self._next_allowed_at - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_allowed_at = now + self._min_interval

    def trigger_cooldown(self) -> None:
        """EGW00201(호출 빈도 제한) 오류가 발생했을 때 추가 cooldown을 적용한다."""
        self._next_allowed_at = max(self._next_allowed_at, time.monotonic() + self._cooldown)
