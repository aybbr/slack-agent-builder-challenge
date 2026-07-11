select
    rm.account_id,
    rm.revenue_month,
    rm.total_revenue,
    rm.invoice_count,
    rm.paid_invoices,
    rm.plan_tier,
    pe.lead_score_tier,
    pe.weighted_pipeline_value,
    fi.forecast_category,
    fi.forecast_revenue,
    case
        when pe.lead_score_tier = 'high' then rm.total_revenue * 1.15
        when pe.lead_score_tier = 'medium' then rm.total_revenue
        else rm.total_revenue * 0.85
    end as adjusted_revenue
from {{ ref('int_revenue_monthly') }} rm
left join {{ ref('int_pipeline_enrichment') }} pe
    on rm.account_id = pe.account_id
left join {{ ref('int_forecast_input') }} fi
    on rm.account_id = fi.account_id
    and rm.revenue_month = fi.revenue_month
