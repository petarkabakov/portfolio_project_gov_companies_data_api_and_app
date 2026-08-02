-- Grain: one row per company_number. Type 1 — latest known attributes only;
-- see fct_company_status_history for the full status-change history.
with ranked as (
    select
        *,
        row_number() over (partition by company_number order by fetched_at desc) as rn
    from {{ ref('stg_company_profiles') }}
)

select
    company_number,
    company_name,
    company_status,
    company_type,
    jurisdiction,
    fetched_at as last_seen_at
from ranked
where rn = 1
