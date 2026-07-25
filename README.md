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
| 2 | dbt models, contracts, tests | ⬜ Not started |
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
  models.
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

## Local development

```bash
uv sync
cp .env.example .env   # add your Companies House API key
uv run pytest
uv run dbt build --target dev
```

## What I would do next

To be written at Phase 6.