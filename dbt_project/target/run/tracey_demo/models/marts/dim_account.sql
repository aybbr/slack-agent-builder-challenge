
  
    
    

    create  table
      "demo"."main_main"."dim_account__dbt_tmp"
  
    as (
      select
    account_id,
    account_name,
    industry,
    region,
    annual_revenue,
    is_partner,
    total_opportunities,
    total_pipeline_value,
    avg_lead_score,
    max_lead_score,
    active_opportunities,
    total_users,
    active_days,
    features_used,
    last_active_date,
    lead_score_tier,
    account_segment
from "demo"."main_intermediate"."int_account_360"
    );
  
  