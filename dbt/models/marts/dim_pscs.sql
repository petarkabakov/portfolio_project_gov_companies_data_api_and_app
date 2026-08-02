-- Grain: one row per (company_number, psc_id). Type 1 — latest known
-- attributes only; see fct_psc_verification_status for the full history.
with ranked as (
    select
        *,
        row_number() over (
            partition by company_number, psc_id order by fetched_at desc
        ) as rn
    from {{ ref('stg_pscs') }}
)

select
    company_number,
    psc_id,
    kind,
    psc_name,
    natures_of_control,
    notified_on,
    ceased_on,
    nationality,
    country_of_residence,
    fetched_at as last_seen_at
from ranked
where rn = 1
