"""Raw persistence layer.

The raw schema is an append-only log of snapshots, not an upsert-by-company
keyed table: ECCTA compliance tracking cares about *when* a company's status
changed, which an upsert-in-place would destroy. Deduplicating to "latest per
company" is deliberately left to dbt staging models (Phase 2).
"""

from datetime import datetime

import psycopg2
from psycopg2.extras import Json

_DDL = """
CREATE SCHEMA IF NOT EXISTS raw;
CREATE TABLE IF NOT EXISTS raw.company_profile_snapshots (
    id             BIGSERIAL PRIMARY KEY,
    company_number TEXT NOT NULL,
    fetched_at     TIMESTAMPTZ NOT NULL,
    http_status    INT NOT NULL,
    payload        JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_company_profile_snapshots_company_number
    ON raw.company_profile_snapshots (company_number, fetched_at DESC);
"""

_INSERT_SQL = """
INSERT INTO raw.company_profile_snapshots (company_number, fetched_at, http_status, payload)
VALUES (%s, %s, %s, %s)
"""


class CompanyProfileRepository:
    """Holds one connection reused across a whole batch run."""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn: psycopg2.extensions.connection | None = None

    def __enter__(self) -> "CompanyProfileRepository":
        self._conn = psycopg2.connect(self._dsn)
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._conn is not None:
            self._conn.close()

    def ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(_DDL)
        self._conn.commit()

    def save_snapshot(
        self, *, company_number: str, payload: dict, fetched_at: datetime, http_status: int
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(_INSERT_SQL, (company_number, fetched_at, http_status, Json(payload)))
        self._conn.commit()
