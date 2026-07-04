
  
  create view "demo"."main_staging"."stg_salesforce__opportunity__dbt_tmp" as (
    select
    opportunity_id,
    customer_id,
    amount,
    stage,
    lead_score,
    close_date,
    created_at
from "demo"."main"."raw_salesforce_opportunity"
  );
