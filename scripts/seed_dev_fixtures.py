"""Seeds raw.* tables with deterministic synthetic data for local dbt
iteration and CI — covering edge cases the live Companies House API won't
reliably exercise on any given run: multiple company-status episodes, an
unrelated field change that should NOT create a new episode, and each
documented shape of identity_verification_details (including its absence).

Usage: DATABASE_URL=... uv run python scripts/seed_dev_fixtures.py

Reuses RawRepository directly rather than a separate seeding mechanism, so
the seeded rows go through the exact same append-only/content-hash-dedup path
real ingestion does.
"""

import os
from datetime import datetime, timezone

from registry_sentinel.repository import RawRepository

COMPANY_NUMBER = "00000006"
OFFICER_ID = "aBcDeF12345"
OFFICER_ID_2 = "gHiJkL67890"
PSC_ID = "XyZ98765"


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


COMPANY_PROFILE_SNAPSHOTS = [
    (
        _dt(2024, 1, 1),
        {
            "company_number": COMPANY_NUMBER,
            "company_name": "EXAMPLE COMPANY LIMITED",
            "company_status": "active",
            "type": "ltd",
            "jurisdiction": "england-wales",
        },
    ),
    (
        # Unrelated field change (accounts.next_due), same company_status —
        # must NOT create a new episode in fct_company_status_history.
        _dt(2025, 3, 1),
        {
            "company_number": COMPANY_NUMBER,
            "company_name": "EXAMPLE COMPANY LIMITED",
            "company_status": "active",
            "type": "ltd",
            "jurisdiction": "england-wales",
            "accounts": {"next_due": "2026-01-01"},
        },
    ),
    (
        _dt(2025, 9, 1),
        {
            "company_number": COMPANY_NUMBER,
            "company_name": "EXAMPLE COMPANY LIMITED",
            "company_status": "voluntary-arrangement",
            "type": "ltd",
            "jurisdiction": "england-wales",
        },
    ),
    (
        _dt(2026, 4, 1),
        {
            "company_number": COMPANY_NUMBER,
            "company_name": "EXAMPLE COMPANY LIMITED",
            "company_status": "dissolved",
            "type": "ltd",
            "jurisdiction": "england-wales",
        },
    ),
]

OFFICER_SNAPSHOTS = [
    # Officer 1: unverified, then verified via the identity_verified_on + ACSP shape.
    (
        OFFICER_ID,
        _dt(2024, 1, 1),
        {
            "name": "SMITH, Jane Ann",
            "officer_role": "director",
            "appointed_on": "2019-03-01",
            "links": {"officer": {"appointments": f"/officers/{OFFICER_ID}/appointments"}},
        },
    ),
    (
        OFFICER_ID,
        _dt(2025, 12, 1),
        {
            "name": "SMITH, Jane Ann",
            "officer_role": "director",
            "appointed_on": "2019-03-01",
            "identity_verification_details": {
                "identity_verified_on": "2025-11-20",
                "authorised_corporate_service_provider_name": "DE PINNA LLP",
            },
            "links": {"officer": {"appointments": f"/officers/{OFFICER_ID}/appointments"}},
        },
    ),
    # Officer 2: verified via the "completion statement, no ACSP" shape only.
    (
        OFFICER_ID_2,
        _dt(2026, 1, 1),
        {
            "name": "DOE, John",
            "officer_role": "secretary",
            "appointed_on": "2020-06-15",
            "identity_verification_details": {"appointment_verification_end_on": "2026-04-16"},
            "links": {"officer": {"appointments": f"/officers/{OFFICER_ID_2}/appointments"}},
        },
    ),
]

PSC_SNAPSHOTS = [
    (
        PSC_ID,
        _dt(2024, 1, 1),
        {
            "kind": "individual-person-with-significant-control",
            "name": "Jane Ann Smith",
            "notified_on": "2019-03-01",
            "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
            "links": {
                "self": (
                    f"/company/{COMPANY_NUMBER}/persons-with-significant-control"
                    f"/individual/{PSC_ID}"
                )
            },
        },
    ),
]


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    with RawRepository(database_url) as repository:
        repository.ensure_schema()

        # This script's whole point is a known, deterministic dataset for dbt
        # iteration/CI — reset the raw tables first so leftover rows from a
        # previous run (or from pytest's integration tests, which share the
        # same company_number "00000006" fixture data) can't silently change
        # mart output between runs.
        repository.truncate_all()

        for fetched_at, payload in COMPANY_PROFILE_SNAPSHOTS:
            repository.save_company_profile(
                company_number=COMPANY_NUMBER,
                payload=payload,
                fetched_at=fetched_at,
                http_status=200,
            )

        for officer_id, fetched_at, payload in OFFICER_SNAPSHOTS:
            repository.save_officer(
                company_number=COMPANY_NUMBER,
                officer_id=officer_id,
                payload=payload,
                fetched_at=fetched_at,
                http_status=200,
            )

        for psc_id, fetched_at, payload in PSC_SNAPSHOTS:
            repository.save_psc(
                company_number=COMPANY_NUMBER,
                psc_id=psc_id,
                payload=payload,
                fetched_at=fetched_at,
                http_status=200,
            )

    print("seeded raw.* tables with deterministic dev fixtures")


if __name__ == "__main__":
    main()
