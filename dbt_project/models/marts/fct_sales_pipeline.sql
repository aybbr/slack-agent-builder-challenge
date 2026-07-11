select
    opportunity_id,
    account_id,
    lead_score_tier,
    account_segment,
    amount,
    stage,
    raw_lead_score as legacy_lead_score,
    close_date,
    created_at,
    weighted_pipeline_value
from {{ ref('int_pipeline_enrichment') }}
