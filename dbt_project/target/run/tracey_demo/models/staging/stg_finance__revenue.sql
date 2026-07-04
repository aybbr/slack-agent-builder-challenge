
  
  create view "demo"."main_staging"."stg_finance__revenue__dbt_tmp" as (
    select
    opportunity_id,
    revenue_amount,
    recognition_date
from "demo"."main"."raw_finance_revenue"
  );
