import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from registry_sentinel.models import CompanyProfile

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "company_profile.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_parses_fixture_payload():
    profile = CompanyProfile.model_validate(load_fixture())

    assert profile.company_number == "00000006"
    assert profile.company_name == "EXAMPLE COMPANY LIMITED"
    assert profile.company_status == "active"
    assert profile.date_of_creation == date(1985, 6, 17)


def test_unknown_fields_are_tolerated():
    payload = load_fixture()
    payload["a_field_companies_house_adds_later"] = "some value"

    profile = CompanyProfile.model_validate(payload)

    assert profile.company_number == "00000006"


def test_missing_company_number_raises():
    payload = load_fixture()
    del payload["company_number"]

    with pytest.raises(ValidationError):
        CompanyProfile.model_validate(payload)
