# Registry Sentinel
[![CI](https://github.com/petarkabakov/portfolio_project_gov_companies_data_api_and_app/actions/workflows/ci.yml/badge.svg)](https://github.com/petarkabakov/portfolio_project_gov_companies_data_api_and_app/actions/workflows/ci.yml)

An audit-ready data platform ingesting UK Companies House data via batch and streaming APIs, enforcing data contracts, testing every model, monitoring freshness and volume, and producing a regulatory-reporting mart that tracks director and PSC identity-verification compliance under the Economic Crime and Corporate Transparency Act (ECCTA).

## Why this exists

ECCTA introduces mandatory identity verification for company directors and People with Significant Control. Verification status is a compliance attribute that propagates through the corporate register: an unverified PSC at the top of an ownership chain has implications for every entity beneath it.

Tracking that reliably is a data engineering problem, not a reporting one. It requires ingestion that survives rate limits and disconnects, models with enforced schemas, tests that fail the build when the data is wrong, and observability that catches silence as well as errors.

## Architecture
Companies House API (REST + Streaming)
│
▼
Python ingestion layer
rate-limit aware · retry/backoff · idempotent
│
▼
Neon Postgres — raw schema
│
▼
dbt — staging → intermediate → marts
enforced contracts · generic + custom tests
│
▼
Dagster — software-defined assets
schedules · sensors · asset checks
│
▼
Observability — source freshness · volume anomaly
│
▼
Streamlit — thin serving layer

GitHub Actions runs lint, unit tests, and a full `dbt build` against a
throwaway Postgres container on every pull request.

## Stack

| Layer | Choice | Rationale |
|---|---|---|
| Ingestion | Python + httpx | Async-capable, first-class testing via respx |
| Warehouse | Neon Postgres | Database branching gives isolated dev and CI environments |
| Transformation | dbt | Contracts, tests, and lineage as first-class artefacts |
| Orchestration | Dagster | Software-defined assets model data dependencies, not task order |
| Serving | Streamlit | Deliberately thin — the consumption layer, not the point |
| CI | GitHub Actions | Every PR proves the project builds on a clean machine |

## Status

| Phase | Scope | Status |
|---|---|---|
| 0 | Foundation — repo, CI, environments | 🟢 Done |
| 1 | Batch ingestion with rate limiting | 🟢 Done |
| 2 | dbt models, contracts, tests | 🟢 Done |
| 3 | Dagster orchestration | ⬜ Not started |
| 4 | Streaming ingestion | ⬜ Not started |
| 5 | Observability | ⬜ Not started |
| 6 | Serving layer | ⬜ Not started |

## Design decisions

Recorded as the project progresses. Each entry states the decision, the
alternative rejected, and the trade-off accepted.

**Phase 1 — Batch ingestion client**

- **Injectable `Clock` protocol over `freezegun`/`time-machine`.** Both the
  proactive rate limiter and tenacity's retry backoff sleep through the same
  `Clock.sleep`, so time-dependent behaviour is deterministic in tests without
  monkeypatching the global `time` module. Trade-off: a small amount of DI
  boilerplate versus a library that patches time globally.
- **Local sliding-window limiter as source of truth, server headers as a
  backstop.** The limiter tracks its own 600-req/5-min window via the clock;
  Companies House's `X-Ratelimit-Remain`/`X-Ratelimit-Reset` response headers
  only set a defensive cooldown when the server reports we're near the limit
  (e.g. a shared key or a restarted process). Trade-off: slightly more
  reconciliation logic in exchange for not trusting wall-clock skew alone.
- **Append-only raw snapshots, not upsert-by-company-number.** Ingestion
  writes an immutable row per fetch (`raw.company_profile_snapshots`) instead
  of updating in place. Trade-off: more storage over time, but preserves the
  history ECCTA compliance tracking needs — an upsert would destroy exactly
  the "when did this change" signal the project exists to capture.
  Deduplicating to "latest per company" is deferred to Phase 2 dbt staging
  models. Idempotency is still enforced, just at the content level rather than
  the row level: each snapshot is uniquely keyed on
  `(company_number, sha256(payload))`, so re-running ingestion against
  unchanged data is a no-op (`ON CONFLICT DO NOTHING`), while a genuinely
  changed payload still lands as a new row.
- **Pagination follows Companies House's `start_index`/`items_per_page`
  convention.** `search_companies` walks pages until a page returns fewer
  items than requested or the API's own `total_results` has been reached,
  whichever fires first — a defensive stop so a missing/inconsistent
  `total_results` can't cause an infinite loop. The same pattern generalises
  to officers/PSC/filing-history endpoints later.
- **`psycopg2-binary` over SQLAlchemy/psycopg3.** Already resolved
  transitively via `dbt-postgres`, so promoting it to a direct dependency adds
  no new lock/supply-chain surface. The repository layer only needs a couple
  of parameterized statements — an ORM isn't warranted yet.
- **Lightweight `extra="allow"` pydantic gate over a full field mapping.**
  `CompanyProfile` only requires the handful of fields the pipeline actually
  depends on; raw JSON, not the model, is what gets persisted. Trade-off: no
  compile-time guarantee about the shape of fields nobody reads yet, in
  exchange for not having to track Companies House's full schema by hand.
- **Log-and-continue batch policy, not fail-fast.** `ingest_batch` records a
  per-company failure and keeps going; the process only signals a hard
  failure (non-zero exit) if every company in the batch failed. A batch of
  hundreds of company numbers will routinely include dissolved companies
  (404s) — aborting on the first one would defeat the point of batch
  ingestion.

**Phase 2 — Officers/PSC ingestion + dbt staging & marts**

- **Extended ingestion before dbt, not after.** The README's flagship mart is
  ECCTA director/PSC compliance, but Phase 1 only ingested company profiles.
  Rather than build an aspirational mart with no real data behind it, officer
  and PSC ingestion (`get_officers`/`get_pscs`, `raw.officer_snapshots`,
  `raw.psc_snapshots`) was added first, reusing every Phase 1 primitive
  (Clock, RateLimiter, tenacity-via-Clock retries) unchanged.
- **Per-item skip-and-log for officers/PSC, unlike `search_companies`.** A
  single malformed officer or PSC record is skipped with a warning rather
  than aborting the whole list — one bad record among many shouldn't cost the
  rest of a company's officers. `search_companies` still propagates
  validation errors, since a single-item mismatch there is a genuine, whole-
  call failure signal, not noise in a list.
- **`RawRepository` generalizes over three identical-shaped raw tables.**
  Company profile, officer, and PSC snapshots are all append-only and
  content-hash-deduped, differing only in table name and natural key — a
  `SnapshotTableSpec`/`SnapshotRepository` pair generates the DDL/inserts for
  all three rather than tripling the same code (`CompanyProfileRepository`
  was renamed to `RawRepository` accordingly).
- **`identity_verification_details` extracted defensively, never assumed
  reliable.** Real-world research (Companies House's own developer forum)
  confirms ECCTA identity verification is mid-rollout (mandatory for existing
  directors/PSCs by 18 Nov 2026) and that this field's shape is genuinely
  inconsistent between records — no canonical schema published as of this
  writing. Staging models extract it via `coalesce()` across the documented
  alternate key names and keep the result as `text`, not a strict typed
  sub-model; this was verified end-to-end against synthetic snapshots
  covering all three real-world shapes (verified-with-ACSP, verified-via-
  completion-statement, and the field's total absence).
- **Staging is a 1:1 typed passthrough; episode-collapsing history logic
  lives once, in intermediate.** Raw's content-hash dedup only catches
  byte-identical whole payloads, so an unrelated field changing (e.g.
  `accounts.next_due`) still produces a new raw row. If staging collapsed to
  "latest per entity," intermediate would have to re-derive full history from
  raw again anyway. Instead, intermediate's `LAG`-based episode logic
  (partitioned per entity, boundary on the one tracked attribute — company
  status or verification state) collapses consecutive-identical-attribute
  rows into a single episode, while unrelated attribute changes are attached
  from the latest snapshot within that episode via a separate join — so a
  name change alone doesn't fracture a status episode.
- **Marts: `dim_companies`/`dim_officers`/`dim_pscs` (Type 1, latest) plus
  `fct_company_status_history`/`fct_officer_verification_status`/
  `fct_psc_verification_status` (one row per change episode), every table
  with an explicitly declared grain, dbt contracts enforced (explicit
  `data_type` per column), and a `dbt_utils.unique_combination_of_columns`
  test enforcing that grain in code, not just in the description.** Verified
  by seeding deterministic synthetic data (`scripts/seed_dev_fixtures.py`)
  covering multiple status episodes, an unrelated-field-change that must
  *not* fracture an episode, and each documented verification-field shape —
  then running a full `dbt build` and inspecting the resulting rows directly,
  not just checking the build succeeded.
- **`dbt-core`/`dbt-postgres` pinned to the matching `1.11.x` line.**
  `dbt-postgres`'s own metadata permits `dbt-core<2.0,>=1.8.0rc1`, which had
  let `uv.lock` float `dbt-core` to `1.12.0` — a version with no matching
  adapter release. dbt ships adapter+core as paired releases; running core
  ahead of its adapter is an avoidable risk, not a benefit.

## Local development

```bash
uv sync
cp .env.example .env   # add your Companies House API key and Neon DATABASE_URL
uv run pytest

# dbt reads discrete PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE vars (see
# dbt/profiles.yml.example), a different convention from the app's single
# DATABASE_URL DSN — derive them from the same .env value before running dbt:
cp dbt/profiles.yml.example dbt/profiles.yml   # gitignored; edit host/user/password/dbname
uv run dbt deps --project-dir dbt --profiles-dir dbt
uv run python scripts/seed_dev_fixtures.py     # deterministic raw.* dataset for local iteration
uv run dbt build --project-dir dbt --profiles-dir dbt --target dev
```

## What I would do next

To be written at Phase 6.