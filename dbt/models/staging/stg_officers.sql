-- 1:1 typed passthrough, no dedup (see stg_company_profiles.sql for why).
--
-- identity_verification_details is genuinely inconsistent-shaped as of this
-- writing (Companies House's own developer forum documents it, no canonical
-- schema published) — extracted defensively via coalesce across the
-- documented alternate key names. Provisional: re-validate against real
-- sampled payloads once officer ingestion is live against the production API.
select
    id as snapshot_id,
    company_number,
    officer_id,
    fetched_at,
    http_status,
    payload_hash,
    payload,
    payload ->> 'name' as officer_name,
    payload ->> 'officer_role' as officer_role,
    (payload ->> 'appointed_on')::date as appointed_on,
    (payload ->> 'resigned_on')::date as resigned_on,
    payload ->> 'nationality' as nationality,
    payload ->> 'country_of_residence' as country_of_residence,
    coalesce(
        payload -> 'identity_verification_details' ->> 'identity_verified_on',
        payload -> 'identity_verification_details' ->> 'appointment_verification_end_on'
    ) as identity_verified_on,
    payload -> 'identity_verification_details' ->> 'authorised_corporate_service_provider_name'
        as acsp_name,
    (payload -> 'identity_verification_details') is not null as has_identity_verification_details
from {{ source('raw', 'officer_snapshots') }}
