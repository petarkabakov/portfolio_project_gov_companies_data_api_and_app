-- 1:1 typed passthrough of every raw company profile snapshot, no dedup here:
-- picking "latest per company" and detecting change episodes both live in
-- the intermediate layer, once, so every downstream mart reuses the same logic.
select
    id as snapshot_id,
    company_number,
    fetched_at,
    http_status,
    payload_hash,
    payload,
    payload ->> 'company_name' as company_name,
    payload ->> 'company_status' as company_status,
    payload ->> 'type' as company_type,
    (payload ->> 'date_of_creation')::date as date_of_creation,
    payload ->> 'jurisdiction' as jurisdiction
from {{ source('raw', 'company_profile_snapshots') }}
