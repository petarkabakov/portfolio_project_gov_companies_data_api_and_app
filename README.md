# Registry Sentinel


An audit-ready data platform ingesting UK Companies House data via batch and
streaming APIs, enforcing data contracts, testing every model, monitoring
freshness and volume, and producing a regulatory-reporting mart that tracks
director and PSC identity-verification compliance under the Economic Crime and
Corporate Transparency Act (ECCTA).

## Why this exists

ECCTA introduces mandatory identity verification for company directors and
People with Significant Control. Verification status is a compliance attribute
that propagates through the corporate register: an unverified PSC at the top of
an ownership chain has implications for every entity beneath it.

Tracking that reliably is a data engineering problem, not a reporting one. It
requires ingestion that survives rate limits and disconnects, models with
enforced schemas, tests that fail the build when the data is wrong, and
observability that catches silence as well as errors.

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
| 0 | Foundation — repo, CI, environments | 🟡 In progress |
| 1 | Batch ingestion with rate limiting | ⬜ Not started |
| 2 | dbt models, contracts, tests | ⬜ Not started |
| 3 | Dagster orchestration | ⬜ Not started |
| 4 | Streaming ingestion | ⬜ Not started |
| 5 | Observability | ⬜ Not started |
| 6 | Serving layer | ⬜ Not started |

## Design decisions

Recorded as the project progresses. Each entry states the decision, the
alternative rejected, and the trade-off accepted.

## Local development

```bash
uv sync
cp .env.example .env   # add your Companies House API key
uv run pytest
uv run dbt build --target dev
```

## What I would do next

To be written at Phase 6.