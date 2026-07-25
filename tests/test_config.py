import pytest
from pydantic import ValidationError

from registry_sentinel.config import Settings


def test_defaults_are_applied():
    settings = Settings(
        _env_file=None,
        companies_house_api_key="test-key",
        database_url="postgresql://user:pass@localhost/db",
    )

    assert settings.companies_house_base_url == "https://api.company-information.service.gov.uk"
    assert settings.rate_limit_max_requests == 600
    assert settings.rate_limit_window_seconds == 300.0
    assert settings.request_timeout_seconds == 10.0
    assert settings.retry_max_attempts == 5


def test_missing_required_field_raises():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, companies_house_api_key="test-key")


def test_explicit_values_override_defaults():
    settings = Settings(
        _env_file=None,
        companies_house_api_key="test-key",
        database_url="postgresql://user:pass@localhost/db",
        rate_limit_max_requests=10,
    )

    assert settings.rate_limit_max_requests == 10
