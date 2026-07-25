"""Sliding-window rate limiter matching Companies House's 600-req/5-min limit.

The local sliding window (driven entirely by the injected Clock) is the source
of truth for proactive scheduling. The server's X-Ratelimit-* response headers
are used only defensively: if the server reports we're near the limit (e.g. a
shared API key, or a restarted process that lost its in-memory window), a
cooldown deadline is set for the next acquire() to honour.
"""

import time
from collections import deque

from registry_sentinel.clock import Clock


class RateLimiter:
    def __init__(
        self,
        clock: Clock,
        max_requests: int = 600,
        window_seconds: float = 300.0,
        safety_margin: int = 1,
    ):
        self._clock = clock
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._safety_margin = safety_margin
        self._timestamps: deque[float] = deque()
        self._cooldown_until: float | None = None

    def acquire(self) -> None:
        now = self._clock.monotonic()

        if self._cooldown_until is not None:
            if now < self._cooldown_until:
                self._clock.sleep(self._cooldown_until - now)
                now = self._clock.monotonic()
            self._cooldown_until = None

        self._evict(now)

        if len(self._timestamps) >= self._max_requests:
            wait_for = self._window_seconds - (now - self._timestamps[0])
            if wait_for > 0:
                self._clock.sleep(wait_for)
                now = self._clock.monotonic()
                self._evict(now)

        self._timestamps.append(now)

    def _evict(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def observe_server_headers(
        self, *, remaining: int, reset_epoch: float, now_epoch: float | None = None
    ) -> None:
        if remaining > self._safety_margin:
            return

        now_epoch = time.time() if now_epoch is None else now_epoch
        delay = reset_epoch - now_epoch
        if delay <= 0:
            return

        candidate = self._clock.monotonic() + delay
        if self._cooldown_until is None or candidate > self._cooldown_until:
            self._cooldown_until = candidate
