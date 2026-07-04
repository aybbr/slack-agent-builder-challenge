select
    opportunity_id,
    revenue_amount,
    recognition_date
from {{ source('raw', 'raw_finance_revenue') }}
