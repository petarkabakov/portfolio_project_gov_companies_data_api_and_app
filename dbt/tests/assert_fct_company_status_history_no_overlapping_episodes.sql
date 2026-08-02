-- Real correctness property of the LAG-episode logic in
-- int_company_profile_history.sql, not just a uniqueness check: an episode
-- must never start at or after its own end. If this ever fires, it means two
-- raw snapshots landed with identical (or out-of-order) fetched_at values for
-- the same company, which the episode window functions assume can't happen.
select *
from {{ ref('fct_company_status_history') }}
where effective_to is not null
  and effective_from >= effective_to
