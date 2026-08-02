"""Raw persistence layer.

The raw schema is an append-only log of snapshots, not an upsert-by-key
table: ECCTA compliance tracking cares about *when* a company/officer/PSC's
attributes changed, which an upsert-in-place would destroy. Deduplicating to
"latest per entity" is deliberately left to dbt staging models.

Three raw tables (company profiles, officers, PSCs) share an identical shape
— append-only, content-hash-deduped — differing only in table name and
natural key, so the DDL/insert generation is driven by a small
SnapshotTableSpec rather than tripled by hand.

Table/column names below come only from the fixed, developer-controlled specs
at the bottom of this module — never from external input — so plain string
formatting is safe here. If this mechanism is ever extended to accept a
dynamically supplied table/column name, switch to psycopg2.sql.Identifier.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

import psycopg2
from psycopg2.extras import Json


def _hash_payload(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SnapshotTableSpec:
    table_name: str
    natural_key_columns: tuple[str, ...]


COMPANY_PROFILE_SNAPSHOTS = SnapshotTableSpec("company_profile_snapshots", ("company_number",))
OFFICER_SNAPSHOTS = SnapshotTableSpec("officer_snapshots", ("company_number", "officer_id"))
PSC_SNAPSHOTS = SnapshotTableSpec("psc_snapshots", ("company_number", "psc_id"))


class SnapshotRepository:
    """DDL/insert generation for one raw.* append-only, content-hash-deduped table."""

    def __init__(self, spec: SnapshotTableSpec):
        self._spec = spec

    def ddl(self) -> str:
        key_column_defs = "\n".join(
            f"    {col} TEXT NOT NULL," for col in self._spec.natural_key_columns
        )
        index_cols = ", ".join([*self._spec.natural_key_columns, "fetched_at DESC"])
        unique_cols = ", ".join([*self._spec.natural_key_columns, "payload_hash"])
        return f"""
CREATE TABLE IF NOT EXISTS raw.{self._spec.table_name} (
    id             BIGSERIAL PRIMARY KEY,
{key_column_defs}
    fetched_at     TIMESTAMPTZ NOT NULL,
    http_status    INT NOT NULL,
    payload        JSONB NOT NULL
);

ALTER TABLE raw.{self._spec.table_name}
    ADD COLUMN IF NOT EXISTS payload_hash TEXT;

CREATE INDEX IF NOT EXISTS ix_{self._spec.table_name}_natural_key
    ON raw.{self._spec.table_name} ({index_cols});

CREATE UNIQUE INDEX IF NOT EXISTS ux_{self._spec.table_name}_natural_key_payload_hash
    ON raw.{self._spec.table_name} ({unique_cols});
"""

    def _insert_sql(self) -> str:
        columns = [*self._spec.natural_key_columns, "fetched_at", "http_status", "payload"]
        columns.append("payload_hash")
        placeholders = ", ".join(["%s"] * len(columns))
        conflict_cols = ", ".join([*self._spec.natural_key_columns, "payload_hash"])
        return (
            f"INSERT INTO raw.{self._spec.table_name} ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_cols}) DO NOTHING"
        )

    def save_snapshot(
        self,
        conn: psycopg2.extensions.connection,
        *,
        natural_key: dict[str, str],
        payload: dict,
        fetched_at: datetime,
        http_status: int,
    ) -> None:
        payload_hash = _hash_payload(payload)
        values = [
            *(natural_key[col] for col in self._spec.natural_key_columns),
            fetched_at,
            http_status,
            Json(payload),
            payload_hash,
        ]
        with conn.cursor() as cur:
            cur.execute(self._insert_sql(), values)


class RawRepository:
    """Holds one connection reused across a whole batch run, writing to all raw.* tables."""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn: psycopg2.extensions.connection | None = None
        self._company_profiles = SnapshotRepository(COMPANY_PROFILE_SNAPSHOTS)
        self._officers = SnapshotRepository(OFFICER_SNAPSHOTS)
        self._pscs = SnapshotRepository(PSC_SNAPSHOTS)

    def __enter__(self) -> "RawRepository":
        self._conn = psycopg2.connect(self._dsn)
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._conn is not None:
            self._conn.close()

    def ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
            for repo in (self._company_profiles, self._officers, self._pscs):
                cur.execute(repo.ddl())
        self._conn.commit()

    def truncate_all(self) -> None:
        """Empties all raw.* tables. For dev/test fixture resets only — never
        called by production ingestion, which is append-only by design.
        """
        with self._conn.cursor() as cur:
            for spec in (COMPANY_PROFILE_SNAPSHOTS, OFFICER_SNAPSHOTS, PSC_SNAPSHOTS):
                cur.execute(f"TRUNCATE TABLE raw.{spec.table_name}")
        self._conn.commit()

    def save_company_profile(
        self, *, company_number: str, payload: dict, fetched_at: datetime, http_status: int
    ) -> None:
        self._company_profiles.save_snapshot(
            self._conn,
            natural_key={"company_number": company_number},
            payload=payload,
            fetched_at=fetched_at,
            http_status=http_status,
        )
        self._conn.commit()

    def save_officer(
        self,
        *,
        company_number: str,
        officer_id: str,
        payload: dict,
        fetched_at: datetime,
        http_status: int,
    ) -> None:
        self._officers.save_snapshot(
            self._conn,
            natural_key={"company_number": company_number, "officer_id": officer_id},
            payload=payload,
            fetched_at=fetched_at,
            http_status=http_status,
        )
        self._conn.commit()

    def save_psc(
        self,
        *,
        company_number: str,
        psc_id: str,
        payload: dict,
        fetched_at: datetime,
        http_status: int,
    ) -> None:
        self._pscs.save_snapshot(
            self._conn,
            natural_key={"company_number": company_number, "psc_id": psc_id},
            payload=payload,
            fetched_at=fetched_at,
            http_status=http_status,
        )
        self._conn.commit()
