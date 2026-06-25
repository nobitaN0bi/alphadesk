"""Circuit breaker for the Dhan HQ adapter (Phase 2.1).

Three-state circuit breaker (CLOSED → OPEN → HALF_OPEN) modelled after the
pattern in
``@temp/QuantDinger/backend_api_python/app/services/live_trading/`` and the
canonical Michael Nygard implementation. We use it to short-circuit Dhan
REST calls when the API is failing repeatedly (e.g. 5xx storms) and
automatically re-probe after a cool-down window.

Transitions:
    CLOSED       — normal; all calls allowed.
    OPEN         — all calls fast-fail with :class:`BreakerOpen`; no network IO.
    HALF_OPEN    — one probe call allowed; if it succeeds, return to CLOSED;
                   if it fails, return to OPEN for another cool-down.

Configurable via env (``DHAN_CIRCUIT_BREAKER_THRESHOLD``,
``DHAN_CIRCUIT_BREAKER_COOLDOWN``).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class BreakerOpen(Exception):
    """Raised when the circuit is OPEN and a call is attempted."""


@dataclass
class CircuitBreaker:
    """Async-safe three-state circuit breaker."""

    failure_threshold: int = 3
    cooldown_seconds: float = 60.0
    name: str = "default"
    _state: BreakerState = field(default=BreakerState.CLOSED)
    _failures: int = 0
    _opened_at: float = 0.0
    _lock: asyncio.Lock = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")
        self._lock = asyncio.Lock()

    @property
    def state(self) -> BreakerState:
        return self._state

    async def _maybe_half_open(self) -> None:
        if (
            self._state is BreakerState.OPEN
            and time.monotonic() - self._opened_at >= self.cooldown_seconds
        ):
            self._state = BreakerState.HALF_OPEN

    async def guard(self) -> None:
        """Raise :class:`BreakerOpen` if the circuit is OPEN. Allows one probe in HALF_OPEN."""
        async with self._lock:
            await self._maybe_half_open()
            if self._state is BreakerState.OPEN:
                raise BreakerOpen(
                    f"circuit '{self.name}' is OPEN (cooldown "
                    f"{self.cooldown_seconds}s remaining)"
                )
            # CLOSED or HALF_OPEN: caller proceeds.

    async def on_success(self) -> None:
        async with self._lock:
            self._failures = 0
            self._state = BreakerState.CLOSED

    async def on_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            if (
                self._state in (BreakerState.CLOSED, BreakerState.HALF_OPEN)
                and self._failures >= self.failure_threshold
            ):
                self._state = BreakerState.OPEN
                self._opened_at = time.monotonic()


__all__ = ["CircuitBreaker", "BreakerState", "BreakerOpen"]
