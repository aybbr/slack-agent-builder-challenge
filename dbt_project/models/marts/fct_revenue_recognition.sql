select
    r.opportunity_id,
    r.revenue_amount,
    r.recognition_date,
    sp.lead_score * 0.3 as lead_score_weighted
from {{ ref('stg_finance__revenue') }} r
join {{ ref('fct_sales_pipeline') }} sp
    on r.opportunity_id = sp.opportunity_id
