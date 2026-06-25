"""Rate limiter for the Dhan HQ adapter (Phase 2.1).

A small, dependency-free token-bucket implementation. Dhan enforces 10 orders/s
on ``/orders`` and tighter limits on other endpoints; this module lets each
endpoint declare its own rate (``RATE_PER_SEC``) and we back-pressure callers
via :func:`acquire` (a sync-friendly ``asyncio.Lock``-guarded sleep).

Inherits the "rate-limited calls" pattern from
``@temp/QuantDinger/backend_api_python/app/services/live_trading/`` but kept
deliberately minimal so we don't pull a new dependency.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass
class TokenBucket:
    """Async-safe token-bucket rate limiter.

    >>> bucket = TokenBucket(rate_per_sec=10, capacity=10)
    >>> await bucket.acquire()  # 0s wait
    True
    """

    rate_per_sec: float
    capacity: float
    _tokens: float = 0.0
    _last: float = 0.0
    _lock: asyncio.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")
        if self.capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> bool:
        """Block until ``tokens`` are available. Always returns True on success."""
        if tokens > self.capacity:
            raise ValueError(
                f"Requested {tokens} tokens but capacity is {self.capacity}"
            )
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_sec)
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                # Need to wait until enough tokens accrue.
                deficit = tokens - self._tokens
                wait_s = deficit / self.rate_per_sec
                # Release the lock while we sleep to keep things fair.
                self._lock.release()
                try:
                    await asyncio.sleep(wait_s)
                finally:
                    await self._lock.acquire()


__all__ = ["TokenBucket"]
