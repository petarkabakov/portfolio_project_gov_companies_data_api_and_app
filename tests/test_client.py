import json
import time
from pathlib import Path

import httpx
import pytest
import respx
from fakes import FakeClock

from registry_sentinel.client import CompaniesHouseClient
from registry_sentinel.config import Settings
from registry_sentinel.exceptions import (
    AuthenticationError,
    CompaniesHouseAPIError,
    CompanyNotFoundError,
    RetriableStatusError,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "company_profile.json").read_text())
BASE_URL = "https://api.company-information.service.gov.uk"


def make_settings(**overrides) -> Settings:
    values = dict(
        _env_file=None,
        companies_house_api_key="test-key",
        database_url="postgresql://user:pass@localhost/db",
        companies_house_base_url=BASE_URL,
        retry_max_attempts=3,
    )
    values.update(overrides)
    return Settings(**values)


def make_client(settings: Settings, clock: FakeClock) -> CompaniesHouseClient:
    return CompaniesHouseClient(settings, clock=clock)


@respx.mock
def test_get_company_profile_success_returns_model_and_raw_dict():
    respx.get(f"{BASE_URL}/company/00000006").mock(return_value=httpx.Response(200, json=FIXTURE))
    client = make_client(make_settings(), FakeClock())

    profile, raw = client.get_company_profile("00000006")

    assert profile.company_number == "00000006"
    assert raw == FIXTURE


@respx.mock
def test_404_raises_company_not_found_immediately():
    respx.get(f"{BASE_URL}/company/nope").mock(return_value=httpx.Response(404))
    client = make_client(make_settings(), FakeClock())

    with pytest.raises(CompanyNotFoundError):
        client.get_company_profile("nope")


@respx.mock
def test_401_raises_authentication_error_immediately():
    respx.get(f"{BASE_URL}/company/00000006").mock(return_value=httpx.Response(401))
    client = make_client(make_settings(), FakeClock())

    with pytest.raises(AuthenticationError):
        client.get_company_profile("00000006")


@respx.mock
def test_unmapped_4xx_raises_companies_house_api_error():
    respx.get(f"{BASE_URL}/company/00000006").mock(return_value=httpx.Response(400))
    client = make_client(make_settings(), FakeClock())

    with pytest.raises(CompaniesHouseAPIError):
        client.get_company_profile("00000006")


@respx.mock
def test_429_with_retry_after_is_retried_and_sleeps_the_exact_duration():
    route = respx.get(f"{BASE_URL}/company/00000006")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "5"}),
        httpx.Response(200, json=FIXTURE),
    ]
    clock = FakeClock()
    client = make_client(make_settings(), clock)

    profile, _ = client.get_company_profile("00000006")

    assert profile.company_number == "00000006"
    assert 5.0 in clock.sleep_calls


@respx.mock
def test_500_retried_up_to_max_attempts_then_raises():
    respx.get(f"{BASE_URL}/company/00000006").mock(return_value=httpx.Response(500))
    client = make_client(make_settings(retry_max_attempts=3), FakeClock())

    with pytest.raises(RetriableStatusError):
        client.get_company_profile("00000006")


@respx.mock
def test_low_remaining_header_causes_next_acquire_to_sleep():
    # X-Ratelimit-Reset is a real Unix epoch second from the server, so the
    # header value is computed relative to wall-clock "now" at test time;
    # the resulting sleep duration is asserted with a small tolerance to
    # absorb the (sub-second) gap between here and _reconcile_from_headers.
    reset_epoch = int(time.time()) + 60
    route = respx.get(f"{BASE_URL}/company/00000006")
    route.side_effect = [
        httpx.Response(
            200,
            json=FIXTURE,
            headers={"X-Ratelimit-Remain": "0", "X-Ratelimit-Reset": str(reset_epoch)},
        ),
        httpx.Response(200, json=FIXTURE),
    ]
    clock = FakeClock()
    client = make_client(make_settings(), clock)

    client.get_company_profile("00000006")
    clock.sleep_calls.clear()
    client.get_company_profile("00000006")

    assert len(clock.sleep_calls) == 1
    assert 58.0 <= clock.sleep_calls[0] <= 60.5


@respx.mock
def test_rate_limiter_is_actually_engaged():
    respx.get(f"{BASE_URL}/company/00000006").mock(return_value=httpx.Response(200, json=FIXTURE))
    clock = FakeClock()
    settings = make_settings(rate_limit_max_requests=1, rate_limit_window_seconds=10.0)
    client = make_client(settings, clock)

    client.get_company_profile("00000006")
    client.get_company_profile("00000006")

    assert clock.sleep_calls == [10.0]
