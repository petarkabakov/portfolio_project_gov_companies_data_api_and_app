-- Grain: one row per (company_number, effective_from) — one row per
-- distinct company_status episode, not per raw snapshot.
select
    company_number,
    company_status,
    company_name,
    company_type,
    jurisdiction,
    effective_from,
    effective_to
from {{ ref('int_company_profile_history') }}
