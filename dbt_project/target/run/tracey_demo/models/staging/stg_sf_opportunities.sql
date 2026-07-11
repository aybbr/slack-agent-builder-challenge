
  
  create view "demo"."main_staging"."stg_sf_opportunities__dbt_tmp" as (
    select
    opportunity_id,
    account_id,
    amount,
    stage,
    lead_score,
    close_date,
    created_at
from "demo"."main"."raw_salesforce_opportunities"
  );
