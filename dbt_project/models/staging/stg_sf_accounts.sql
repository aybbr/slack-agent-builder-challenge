select
    account_id,
    account_name,
    industry,
    region,
    annual_revenue,
    employee_count,
    is_partner
from {{ source('raw', 'raw_salesforce_accounts') }}
