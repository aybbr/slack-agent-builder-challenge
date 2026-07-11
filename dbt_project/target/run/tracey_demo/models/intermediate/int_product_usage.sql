
  
  create view "demo"."main_intermediate"."int_product_usage__dbt_tmp" as (
    select
    pe.account_id,
    a.account_name,
    a.industry,
    a.region,
    pe.feature_id,
    pe.event_type,
    sum(pe.user_count) as total_users,
    count(distinct pe.event_date) as active_days,
    count(distinct pe.feature_id) as features_used,
    max(pe.event_date) as last_active_date
from "demo"."main_staging"."stg_product_events" pe
left join "demo"."main_staging"."stg_sf_accounts" a
    on pe.account_id = a.account_id
group by pe.account_id, a.account_name, a.industry, a.region, pe.feature_id, pe.event_type
  );
