from fakes import FakeClock

from registry_sentinel.rate_limiter import RateLimiter


def test_acquire_does_not_sleep_when_under_limit():
    clock = FakeClock()
    limiter = RateLimiter(clock, max_requests=3, window_seconds=10.0)

    limiter.acquire()
    limiter.acquire()

    assert clock.sleep_calls == []


def test_acquire_sleeps_when_window_is_full():
    clock = FakeClock()
    limiter = RateLimiter(clock, max_requests=2, window_seconds=10.0)

    limiter.acquire()  # t=0
    limiter.acquire()  # t=0
    limiter.acquire()  # window full, must wait until t=10

    assert clock.sleep_calls == [10.0]
    assert clock.monotonic() == 10.0


def test_stale_timestamps_are_evicted_before_checking_the_limit():
    clock = FakeClock()
    limiter = RateLimiter(clock, max_requests=2, window_seconds=10.0)

    limiter.acquire()  # t=0
    clock.sleep(11.0)  # advance past the window without going through acquire()
    limiter.acquire()  # t=11, first timestamp is stale -> only 1 in-window
    limiter.acquire()  # t=11, now 2 in-window, still fine

    assert clock.sleep_calls == [11.0]


def test_observe_server_headers_sets_cooldown_when_remaining_is_low():
    clock = FakeClock()
    limiter = RateLimiter(clock, max_requests=600, window_seconds=300.0, safety_margin=1)

    limiter.observe_server_headers(remaining=0, reset_epoch=100.0, now_epoch=40.0)
    limiter.acquire()

    assert clock.sleep_calls == [60.0]


def test_observe_server_headers_ignored_when_remaining_is_healthy():
    clock = FakeClock()
    limiter = RateLimiter(clock, max_requests=600, window_seconds=300.0, safety_margin=1)

    limiter.observe_server_headers(remaining=500, reset_epoch=100.0, now_epoch=40.0)
    limiter.acquire()

    assert clock.sleep_calls == []


def test_cooldown_is_not_shortened_by_a_less_urgent_header():
    clock = FakeClock()
    limiter = RateLimiter(clock, max_requests=600, window_seconds=300.0, safety_margin=1)

    limiter.observe_server_headers(remaining=0, reset_epoch=100.0, now_epoch=40.0)  # +60
    limiter.observe_server_headers(remaining=0, reset_epoch=50.0, now_epoch=40.0)  # +10, shorter
    limiter.acquire()

    assert clock.sleep_calls == [60.0]
