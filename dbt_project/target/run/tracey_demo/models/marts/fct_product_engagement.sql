
  
    
    

    create  table
      "demo"."main_main"."fct_product_engagement__dbt_tmp"
  
    as (
      select
    account_id,
    feature_id,
    event_type,
    total_users,
    active_days,
    features_used,
    last_active_date
from "demo"."main_intermediate"."int_product_usage"
    );
  
  