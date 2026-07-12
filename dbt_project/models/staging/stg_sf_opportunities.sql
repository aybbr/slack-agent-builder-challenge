select
    opportunity_id as opportunity_uuid,
    account_id,
    amount,
    stage,
    lead_score,
    close_date,
    created_at
from {{ source('raw', 'raw_salesforce_opportunities') }}
