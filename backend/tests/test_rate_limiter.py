import time

from app.trading.broker.rate_limiter import RateLimiter


async def test_acquire_enforces_min_interval() -> None:
    limiter = RateLimiter(min_interval_seconds=0.2, cooldown_seconds=1.0)

    start = time.monotonic()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = time.monotonic() - start

    assert elapsed >= 0.2


async def test_trigger_cooldown_extends_next_wait() -> None:
    limiter = RateLimiter(min_interval_seconds=0.05, cooldown_seconds=0.3)

    await limiter.acquire()
    limiter.trigger_cooldown()

    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start

    assert elapsed >= 0.25
