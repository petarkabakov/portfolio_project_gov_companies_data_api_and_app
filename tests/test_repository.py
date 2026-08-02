from datetime import datetime, timezone

import psycopg2
import pytest

from registry_sentinel.repository import RawRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def repository(postgres_dsn: str):
    with RawRepository(postgres_dsn) as repo:
        repo.ensure_schema()
        repo.truncate_all()
        yield repo


def _save_company_profile(repository: RawRepository, payload: dict, fetched_at: datetime) -> None:
    repository.save_company_profile(
        company_number="00000006", payload=payload, fetched_at=fetched_at, http_status=200
    )


def _save_officer(repository: RawRepository, payload: dict, fetched_at: datetime) -> None:
    repository.save_officer(
        company_number="00000006",
        officer_id="off1",
        payload=payload,
        fetched_at=fetched_at,
        http_status=200,
    )


def _save_psc(repository: RawRepository, payload: dict, fetched_at: datetime) -> None:
    repository.save_psc(
        company_number="00000006",
        psc_id="psc1",
        payload=payload,
        fetched_at=fetched_at,
        http_status=200,
    )


ENTITY_CASES = [
    ("company_profile_snapshots", _save_company_profile, "company_number = '00000006'"),
    (
        "officer_snapshots",
        _save_officer,
        "company_number = '00000006' AND officer_id = 'off1'",
    ),
    ("psc_snapshots", _save_psc, "company_number = '00000006' AND psc_id = 'psc1'"),
]
ENTITY_IDS = [case[0] for case in ENTITY_CASES]


def _count(postgres_dsn: str, table_name: str, where_clause: str) -> int:
    with psycopg2.connect(postgres_dsn) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM raw.{table_name} WHERE {where_clause}")
        (count,) = cur.fetchone()
    return count


def test_ensure_schema_is_idempotent(repository: RawRepository):
    repository.ensure_schema()
    repository.ensure_schema()


@pytest.mark.parametrize(("table_name", "save", "where_clause"), ENTITY_CASES, ids=ENTITY_IDS)
def test_identical_payload_loaded_twice_produces_only_one_row(
    repository: RawRepository, postgres_dsn: str, table_name, save, where_clause
):
    payload = {"status": "active"}

    save(repository, payload, datetime(2026, 1, 1, tzinfo=timezone.utc))
    save(repository, payload, datetime(2026, 1, 2, tzinfo=timezone.utc))

    assert _count(postgres_dsn, table_name, where_clause) == 1


@pytest.mark.parametrize(("table_name", "save", "where_clause"), ENTITY_CASES, ids=ENTITY_IDS)
def test_changed_payload_is_persisted_as_a_new_row(
    repository: RawRepository, postgres_dsn: str, table_name, save, where_clause
):
    save(repository, {"status": "active"}, datetime(2026, 1, 1, tzinfo=timezone.utc))
    save(repository, {"status": "dissolved"}, datetime(2026, 6, 1, tzinfo=timezone.utc))

    assert _count(postgres_dsn, table_name, where_clause) == 2


def test_save_company_profile_round_trips_payload(repository: RawRepository, postgres_dsn: str):
    payload = {"company_number": "00000006", "company_name": "EXAMPLE COMPANY LIMITED"}
    fetched_at = datetime(2026, 7, 1, tzinfo=timezone.utc)

    repository.save_company_profile(
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
