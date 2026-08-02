-- Grain: one row per (company_number, officer_id, effective_from) — one row
-- per verification-status-change episode.
select
    company_number,
    officer_id,
    is_identity_verified,
    officer_name,
    officer_role,
    appointed_on,
    resigned_on,
    identity_verified_on,
    acsp_name,
    effective_from,
    effective_to
from {{ ref('int_officer_verification_history') }}
