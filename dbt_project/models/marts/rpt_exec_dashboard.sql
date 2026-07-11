select
    da.account_id,
    da.account_name,
    da.industry,
    da.region,
    da.account_segment,
    da.lead_score_tier,
    da.total_pipeline_value,
    da.total_users,
    da.features_used,
    fr.total_revenue,
    fr.adjusted_revenue,
    fr.forecast_category,
    fr.forecast_revenue,
    pe.last_active_date,
    case
        when fr.forecast_category = 'growth' then 'expanding'
        when da.total_users > 100 then 'high_engagement'
        when da.total_pipeline_value > 500000 then 'high_value'
        else 'monitor'
    end as executive_summary_flag
from {{ ref('dim_account') }} da
left join {{ ref('fct_revenue') }} fr
    on da.account_id = fr.account_id
left join {{ ref('fct_product_engagement') }} pe
    on da.account_id = pe.account_id
