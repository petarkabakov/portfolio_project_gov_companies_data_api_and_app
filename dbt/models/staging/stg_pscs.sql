-- 1:1 typed passthrough, no dedup (see stg_company_profiles.sql for why).
-- identity_verification_details extraction is defensive/provisional — same
-- caveat as stg_officers.sql.
select
    id as snapshot_id,
    company_number,
    psc_id,
    fetched_at,
    http_status,
    payload_hash,
    payload,
    payload ->> 'kind' as kind,
    payload ->> 'name' as psc_name,
    (payload ->> 'notified_on')::date as notified_on,
    (payload ->> 'ceased_on')::date as ceased_on,
    payload ->> 'nationality' as nationality,
    payload ->> 'country_of_residence' as country_of_residence,
    payload -> 'natures_of_control' as natures_of_control,
    coalesce(
        payload -> 'identity_verification_details' ->> 'identity_verified_on',
        payload -> 'identity_verification_details' ->> 'appointment_verification_end_on'
    ) as identity_verified_on,
    payload -> 'identity_verification_details' ->> 'authorised_corporate_service_provider_name'
        as acsp_name,
    (payload -> 'identity_verification_details') is not null as has_identity_verification_details
from {{ source('raw', 'psc_snapshots') }}
