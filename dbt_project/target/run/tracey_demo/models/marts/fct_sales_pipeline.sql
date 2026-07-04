
  
    
    

    create  table
      "demo"."main_main"."fct_sales_pipeline__dbt_tmp"
  
    as (
      select
    opportunity_id,
    customer_id,
    amount,
    stage,
    lead_score,
    close_date,
    created_at
from "demo"."main_staging"."stg_salesforce__opportunity"
    );
  
  