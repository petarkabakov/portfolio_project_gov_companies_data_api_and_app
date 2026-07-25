"""Injectable clock abstraction so time-dependent logic (rate limiting, retry
backoff) can be driven deterministically in tests instead of sleeping for real.
"""

import time
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)
