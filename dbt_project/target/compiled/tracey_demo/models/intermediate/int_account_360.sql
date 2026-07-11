select
    acs.account_id,
    acs.account_name,
    acs.industry,
    acs.region,
    acs.annual_revenue,
    acs.is_partner,
    acs.total_opportunities,
    acs.total_pipeline_value,
    acs.avg_lead_score,
    acs.max_lead_score,
    acs.active_opportunities,
    pu.total_users,
    pu.active_days,
    pu.features_used,
    pu.last_active_date,
    case
        when acs.avg_lead_score >= 80 then 'high'
        when acs.avg_lead_score >= 50 then 'medium'
        else 'low'
    end as lead_score_tier,
    case
        when acs.is_partner and acs.total_pipeline_value > 100000 then 'premier'
        when acs.is_partner then 'partner'
        when acs.annual_revenue > 1000000 then 'enterprise'
        when acs.annual_revenue > 100000 then 'mid_market'
        else 'smb'
    end as account_segment
from "demo"."main_intermediate"."int_account_score" acs
left join "demo"."main_intermediate"."int_product_usage" pu
    on acs.account_id = pu.account_id
    and acs.industry = pu.industry