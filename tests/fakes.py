"""Test-only fakes. Kept out of src/ so production code carries no test-only branches."""


class FakeClock:
    """A Clock that advances a virtual counter on sleep() instead of blocking."""

    def __init__(self, start: float = 0.0):
        self._now = start
        self.sleep_calls: list[float] = []

    def monotonic(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self._now += seconds
