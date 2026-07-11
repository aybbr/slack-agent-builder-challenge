select
    o.opportunity_id,
    a360.account_id,
    a360.lead_score_tier,
    a360.account_segment,
    o.amount,
    o.stage,
    o.lead_score as raw_lead_score,
    o.close_date,
    o.created_at,
    case
        when a360.lead_score_tier = 'high' then o.amount * 1.2
        when a360.lead_score_tier = 'medium' then o.amount
        else o.amount * 0.8
    end as weighted_pipeline_value
from {{ ref('stg_sf_opportunities') }} o
left join {{ ref('int_account_360') }} a360
    on o.account_id = a360.account_id
