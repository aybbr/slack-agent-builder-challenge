select
    opportunity_id,
    account_id,
    amount,
    stage,
    lead_score,
    close_date,
    created_at
from "demo"."main"."raw_salesforce_opportunities"