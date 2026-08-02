-- Same pattern as int_officer_verification_history.sql, partitioned per
-- (company_number, psc_id).
with ordered as (
    select
        *,
        lag(has_identity_verification_details) over (
            partition by company_number, psc_id order by fetched_at
        ) as prev_has_verification
    from {{ ref('stg_pscs') }}
),

flagged as (
    select
        *,
        (prev_has_verification is distinct from has_identity_verification_details)
            as is_new_episode
    from ordered
),

episodes as (
    select
        *,
        sum(case when is_new_episode then 1 else 0 end)
            over (partition by company_number, psc_id order by fetched_at) as episode_id
    from flagged
),

collapsed as (
    select
        company_number,
        psc_id,
        has_identity_verification_details,
        episode_id,
        min(fetched_at) as effective_from
    from episodes
    group by company_number, psc_id, has_identity_verification_details, episode_id
),

latest_attributes as (
    select distinct on (company_number, psc_id, episode_id)
        company_number,
        psc_id,
        episode_id,
        kind,
        psc_name,
        natures_of_control,
        notified_on,
        ceased_on,
        identity_verified_on,
        acsp_name
    from episodes
    order by company_number asc, psc_id asc, episode_id asc, fetched_at desc
)

select
    collapsed.company_number,
    collapsed.psc_id,
    collapsed.has_identity_verification_details as is_identity_verified,
    latest_attributes.kind,
    latest_attributes.psc_name,
    latest_attributes.natures_of_control,
    latest_attributes.notified_on,
    latest_attributes.ceased_on,
    latest_attributes.identity_verified_on,
    latest_attributes.acsp_name,
    collapsed.effective_from,
    lead(collapsed.effective_from) over (
        partition by collapsed.company_number, collapsed.psc_id order by collapsed.effective_from
    ) as effective_to
from collapsed
inner join latest_attributes
    on
        collapsed.company_number = latest_attributes.company_number
        and collapsed.psc_id = latest_attributes.psc_id
        and collapsed.episode_id = latest_attributes.episode_id
