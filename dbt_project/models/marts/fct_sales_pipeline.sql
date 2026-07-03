select
    opportunity_id,
    customer_id,
    amount,
    stage,
    lead_score,
    close_date,
    created_at
from {{ ref('stg_salesforce__opportunity') }}
