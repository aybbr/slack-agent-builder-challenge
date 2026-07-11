
  
  create view "demo"."main_staging"."stg_sf_accounts__dbt_tmp" as (
    select
    account_id,
    account_name,
    industry,
    region,
    annual_revenue,
    employee_count,
    is_partner
from "demo"."main"."raw_salesforce_accounts"
  );
