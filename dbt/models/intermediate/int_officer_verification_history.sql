-- Same episode-collapsing pattern as int_company_profile_history.sql, but
-- partitioned per (company_number, officer_id) and tracking
-- has_identity_verification_details as the episode boundary — the
-- compliance-relevant "verified vs not" transition. identity_verified_on/
-- acsp_name are attached from the latest snapshot within the episode.
with ordered as (
    select
        *,
        lag(has_identity_verification_details) over (
            partition by company_number, officer_id order by fetched_at
        ) as prev_has_verification
    from {{ ref('stg_officers') }}
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
            over (partition by company_number, officer_id order by fetched_at) as episode_id
    from flagged
),

collapsed as (
    select
        company_number,
        officer_id,
        has_identity_verification_details,
        episode_id,
        min(fetched_at) as effective_from
    from episodes
    group by company_number, officer_id, has_identity_verification_details, episode_id
),

latest_attributes as (
    select distinct on (company_number, officer_id, episode_id)
        company_number,
        officer_id,
        episode_id,
        officer_name,
        officer_role,
        appointed_on,
        resigned_on,
        identity_verified_on,
        acsp_name
    from episodes
    order by company_number asc, officer_id asc, episode_id asc, fetched_at desc
)

select
    collapsed.company_number,
    collapsed.officer_id,
    collapsed.has_identity_verification_details as is_identity_verified,
    latest_attributes.officer_name,
    latest_attributes.officer_role,
    latest_attributes.appointed_on,
    latest_attributes.resigned_on,
    latest_attributes.identity_verified_on,
    latest_attributes.acsp_name,
    collapsed.effective_from,
    lead(collapsed.effective_from) over (
        partition by collapsed.company_number, collapsed.officer_id
        order by collapsed.effective_from
    ) as effective_to
from collapsed
inner join latest_attributes
    on
        collapsed.company_number = latest_attributes.company_number
        and collapsed.officer_id = latest_attributes.officer_id
        and collapsed.episode_id = latest_attributes.episode_id
