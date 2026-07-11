
  
  create view "demo"."main_intermediate"."int_account_score__dbt_tmp" as (
    select
    a.account_id,
    a.account_name,
    a.industry,
    a.region,
    a.annual_revenue,
    a.is_partner,
    count(distinct o.opportunity_id) as total_opportunities,
    sum(o.amount) as total_pipeline_value,
    avg(o.lead_score) as avg_lead_score,
    max(o.lead_score) as max_lead_score,
    count(distinct case when o.stage in ('closed_won', 'negotiation') then o.opportunity_id end) as active_opportunities
from "demo"."main_staging"."stg_sf_accounts" a
left join "demo"."main_staging"."stg_sf_opportunities" o
    on a.account_id = o.account_id
group by a.account_id, a.account_name, a.industry, a.region, a.annual_revenue, a.is_partner
  );
