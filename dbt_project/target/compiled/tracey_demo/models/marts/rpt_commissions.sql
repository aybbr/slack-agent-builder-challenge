select
    sp.account_id,
    sp.opportunity_id,
    sp.amount,
    sp.lead_score_tier,
    sp.weighted_pipeline_value,
    r.adjusted_revenue,
    case
        when sp.lead_score_tier = 'high' then sp.amount * 0.12
        when sp.lead_score_tier = 'medium' then sp.amount * 0.08
        else sp.amount * 0.05
    end as commission,
    r.revenue_month
from "demo"."main_main"."fct_sales_pipeline" sp
left join "demo"."main_main"."fct_revenue" r
    on sp.account_id = r.account_id