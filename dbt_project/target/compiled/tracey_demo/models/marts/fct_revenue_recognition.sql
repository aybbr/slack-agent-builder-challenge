select
    r.opportunity_id,
    r.revenue_amount,
    r.recognition_date,
    sp.lead_score * 0.3 as lead_score_weighted
from "demo"."main_staging"."stg_finance__revenue" r
join "demo"."main_main"."fct_sales_pipeline" sp
    on r.opportunity_id = sp.opportunity_id