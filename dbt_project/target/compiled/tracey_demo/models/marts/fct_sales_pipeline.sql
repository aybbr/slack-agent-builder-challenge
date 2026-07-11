select
    opportunity_id,
    account_id,
    lead_score_tier,
    account_segment,
    amount,
    stage,
    raw_lead_score,
    close_date,
    created_at,
    weighted_pipeline_value
from "demo"."main_intermediate"."int_pipeline_enrichment"