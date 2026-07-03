select
    opportunity_id,
    customer_id,
    amount,
    stage,
    lead_score,
    close_date,
    created_at
from {{ source('raw', 'raw_salesforce_opportunity') }}
