
  
    
    

    create  table
      "demo"."main_main"."dim_customer__dbt_tmp"
  
    as (
      select
    customer_id,
    customer_name,
    industry,
    region
from "demo"."main_staging"."stg_customer"
    );
  
  