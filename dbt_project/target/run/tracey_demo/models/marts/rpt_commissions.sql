
  
    
    

    create  table
      "demo"."main_main"."rpt_commissions__dbt_tmp"
  
    as (
      select
    sp.opportunity_id,
    sp.amount,
    sp.lead_score,
    rr.lead_score_weighted,
    case
        when rr.lead_score_weighted > 10
            then sp.amount * 0.10
        else sp.amount * 0.05
    end as commission
from "demo"."main_main"."fct_sales_pipeline" sp
left join "demo"."main_main"."fct_revenue_recognition" rr
    on sp.opportunity_id = rr.opportunity_id
    );
  
  