from datetime import datetime, timezone

import psycopg2
import pytest

from registry_sentinel.repository import CompanyProfileRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def repository(postgres_dsn: str):
    with CompanyProfileRepository(postgres_dsn) as repo:
        repo.ensure_schema()
        with psycopg2.connect(postgres_dsn) as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE raw.company_profile_snapshots")
            conn.commit()
        yield repo


def test_ensure_schema_is_idempotent(repository: CompanyProfileRepository):
    repository.ensure_schema()
    repository.ensure_schema()


def test_save_snapshot_round_trips_payload(repository: CompanyProfileRepository, postgres_dsn: str):
    payload = {"company_number": "00000006", "company_name": "EXAMPLE COMPANY LIMITED"}
    fetched_at = datetime(2026, 7, 1, tzinfo=timezone.utc)

    repository.save_snapshot(
        company_number="00000006", payload=payload, fetched_at=fetched_at, http_status=200
    )

    with psycopg2.connect(postgres_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT company_number, http_status, payload "
            "FROM raw.company_profile_snapshots WHERE company_number = %s",
            ("00000006",),
        )
        rows = cur.fetchall()

    assert len(rows) == 1
    company_number, http_status, stored_payload = rows[0]
    assert company_number == "00000006"
    assert http_status == 200
    assert stored_payload == payload


def test_changed_payload_for_same_company_is_persisted_as_a_new_row(
    repository: CompanyProfileRepository, postgres_dsn: str
):
    first_fetch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    second_fetch = datetime(2026, 6, 1, tzinfo=timezone.utc)

    repository.save_snapshot(
        company_number="00000006",
        payload={"company_status": "active"},
        fetched_at=first_fetch,
        http_status=200,
    )
    repository.save_snapshot(
        company_number="00000006",
        payload={"company_status": "dissolved"},
        fetched_at=second_fetch,
        http_status=200,
    )

    with psycopg2.connect(postgres_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM raw.company_profile_snapshots WHERE company_number = %s",
            ("00000006",),
        )
        (count,) = cur.fetchone()

    assert count == 2


def test_identical_payload_loaded_twice_produces_only_one_row(
    repository: CompanyProfileRepository, postgres_dsn: str
):
    payload = {"company_number": "00000006", "company_status": "active"}
    first_fetch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    second_fetch = datetime(2026, 1, 2, tzinfo=timezone.utc)

    repository.save_snapshot(
        company_number="00000006", payload=payload, fetched_at=first_fetch, http_status=200
    )
    repository.save_snapshot(
        company_number="00000006", payload=payload, fetched_at=second_fetch, http_status=200
    )

    with psycopg2.connect(postgres_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM raw.company_profile_snapshots WHERE company_number = %s",
            ("00000006",),
        )
        (count,) = cur.fetchone()

    assert count == 1
