-- Collapses stg_company_profiles into status-change episodes. The episode
-- boundary is company_status ONLY (via lag/running-sum), not the other
-- descriptive attributes (name/type/jurisdiction) — those are attached from
-- the latest snapshot within each episode via a separate join, so an
-- unrelated name change doesn't fracture a status episode. This matters
-- because raw's content-hash dedup only catches byte-identical whole
-- payloads: any field changing produces a new raw row, so a snapshot-grained
-- fact table would show noise episodes with no actual status change.
with ordered as (
    select
        *,
        lag(company_status) over (partition by company_number order by fetched_at)
            as prev_status
    from {{ ref('stg_company_profiles') }}
),

flagged as (
    select
        *,
        (prev_status is distinct from company_status) as is_new_episode
    from ordered
),

episodes as (
    select
        *,
        sum(case when is_new_episode then 1 else 0 end)
            over (partition by company_number order by fetched_at) as episode_id
    from flagged
),

collapsed as (
    select
        company_number,
        company_status,
        episode_id,
        min(fetched_at) as effective_from
    from episodes
    group by company_number, company_status, episode_id
),

latest_attributes as (
    select distinct on (company_number, episode_id)
        company_number,
        episode_id,
        company_name,
        company_type,
        jurisdiction
    from episodes
    order by company_number asc, episode_id asc, fetched_at desc
)

select
    collapsed.company_number,
    collapsed.company_status,
    latest_attributes.company_name,
    latest_attributes.company_type,
    latest_attributes.jurisdiction,
    collapsed.effective_from,
    lead(collapsed.effective_from) over (
        partition by collapsed.company_number order by collapsed.effective_from
    ) as effective_to
from collapsed
inner join latest_attributes
    on
        collapsed.company_number = latest_attributes.company_number
        and collapsed.episode_id = latest_attributes.episode_id
