
  
  create view "demo"."main_intermediate"."int_forecast_input__dbt_tmp" as (
    select
    rm.account_id,
    rm.revenue_month,
    rm.total_revenue,
    rm.invoice_count,
    rm.paid_invoices,
    rm.plan_tier,
    pe.lead_score_tier,
    pe.weighted_pipeline_value,
    case
        when pe.weighted_pipeline_value > 100000 and rm.total_revenue > 50000 then 'growth'
        when pe.weighted_pipeline_value > 50000 then 'pipeline_driven'
        when rm.total_revenue > 30000 then 'revenue_driven'
        else 'stable'
    end as forecast_category,
    rm.total_revenue + coalesce(pe.weighted_pipeline_value * 0.3, 0) as forecast_revenue
from "demo"."main_intermediate"."int_revenue_monthly" rm
left join "demo"."main_intermediate"."int_pipeline_enrichment" pe
    on rm.account_id = pe.account_id
  );
