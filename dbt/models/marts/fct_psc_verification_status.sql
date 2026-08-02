-- Grain: one row per (company_number, psc_id, effective_from) — one row per
-- verification-status-change episode.
select
    company_number,
    psc_id,
    is_identity_verified,
    kind,
    psc_name,
    natures_of_control,
    notified_on,
    ceased_on,
    identity_verified_on,
    acsp_name,
    effective_from,
    effective_to
from {{ ref('int_psc_verification_history') }}
