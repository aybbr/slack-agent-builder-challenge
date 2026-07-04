
  
  create view "demo"."main_staging"."stg_customer__dbt_tmp" as (
    select
    customer_id,
    customer_name,
    industry,
    region
from "demo"."main"."raw_customer"
  );
