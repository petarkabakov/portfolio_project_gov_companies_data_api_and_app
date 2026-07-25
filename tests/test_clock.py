import time

from registry_sentinel.clock import RealClock


def test_real_clock_monotonic_is_non_decreasing():
    clock = RealClock()
    first = clock.monotonic()
    second = clock.monotonic()
    assert second >= first


def test_real_clock_sleep_delegates_to_time_sleep(monkeypatch):
    calls = []
    monkeypatch.setattr(time, "sleep", lambda seconds: calls.append(seconds))

    RealClock().sleep(1.5)

    assert calls == [1.5]


def test_real_clock_sleep_skips_non_positive_durations(monkeypatch):
    calls = []
    monkeypatch.setattr(time, "sleep", lambda seconds: calls.append(seconds))

    RealClock().sleep(0)
    RealClock().sleep(-1)

    assert calls == []
