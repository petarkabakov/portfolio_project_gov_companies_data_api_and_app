import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from registry_sentinel.models import (
    CompanyOfficer,
    CompanyProfile,
    PersonWithSignificantControl,
    extract_officer_id,
    extract_psc_id,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_PATH = FIXTURES_DIR / "company_profile.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def load_officer_fixture() -> dict:
    return json.loads((FIXTURES_DIR / "officer.json").read_text())


def load_psc_fixture() -> dict:
    return json.loads((FIXTURES_DIR / "psc.json").read_text())


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


def test_officer_parses_identity_verification_details_shape_with_acsp():
    officer = CompanyOfficer.model_validate(load_officer_fixture())

    assert officer.name == "SMITH, Jane Ann"
    assert officer.officer_role == "director"
    assert officer.identity_verification_details["identity_verified_on"] == "2025-07-16"
    assert (
        officer.identity_verification_details["authorised_corporate_service_provider_name"]
        == "DE PINNA LLP"
    )


def test_officer_tolerates_missing_identity_verification_details():
    payload = load_officer_fixture()
    del payload["identity_verification_details"]

    officer = CompanyOfficer.model_validate(payload)

    assert officer.identity_verification_details is None


def test_officer_missing_name_raises():
    payload = load_officer_fixture()
    del payload["name"]

    with pytest.raises(ValidationError):
        CompanyOfficer.model_validate(payload)


def test_psc_parses_fixture_with_no_identity_verification_details():
    psc = PersonWithSignificantControl.model_validate(load_psc_fixture())

    assert psc.kind == "individual-person-with-significant-control"
    assert psc.name == "Jane Ann Smith"
    assert psc.identity_verification_details is None


def test_psc_missing_kind_raises():
    payload = load_psc_fixture()
    del payload["kind"]

    with pytest.raises(ValidationError):
        PersonWithSignificantControl.model_validate(payload)


def test_extract_officer_id_parses_the_appointments_link():
    assert extract_officer_id(load_officer_fixture()) == "aBcDeF12345"


def test_extract_officer_id_returns_none_when_link_is_missing():
    assert extract_officer_id({"links": {}}) is None
    assert extract_officer_id({}) is None


def test_extract_psc_id_parses_the_self_link():
    assert extract_psc_id(load_psc_fixture()) == "XyZ98765"


def test_extract_psc_id_returns_none_when_link_is_missing():
    assert extract_psc_id({"links": {}}) is None
    assert extract_psc_id({}) is None
