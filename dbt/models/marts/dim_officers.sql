-- Grain: one row per (company_number, officer_id). Type 1 — latest known
-- attributes only; see fct_officer_verification_status for the full history.
-- Known limitation: officer_id is parsed from a person-level appointments
-- URL, not appointment-scoped — a rare re-appointment at the same company
-- would collapse under "latest wins" here.
with ranked as (
    select
        *,
        row_number() over (
            partition by company_number, officer_id order by fetched_at desc
        ) as rn
    from {{ ref('stg_officers') }}
)

select
    company_number,
    officer_id,
    officer_name,
    officer_role,
    appointed_on,
    resigned_on,
    nationality,
    country_of_residence,
    fetched_at as last_seen_at
from ranked
where rn = 1
