
  
  create view "demo"."main_staging"."stg_product_events__dbt_tmp" as (
    select
    event_id,
    account_id,
    feature_id,
    event_type,
    user_count,
    event_date
from "demo"."main"."raw_product_events"
  );
