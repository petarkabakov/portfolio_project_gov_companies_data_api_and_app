-- Every officer verification-status episode must belong to an officer that
-- also exists in dim_officers. Composite-key relationships aren't supported
-- by the built-in `relationships` generic test, hence this singular test.
select
    fct.company_number,
    fct.officer_id
from {{ ref('fct_officer_verification_status') }} as fct
left join {{ ref('dim_officers') }} as dim
    on fct.company_number = dim.company_number
    and fct.officer_id = dim.officer_id
where dim.company_number is null
