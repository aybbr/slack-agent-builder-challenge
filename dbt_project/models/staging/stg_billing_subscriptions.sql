select
    subscription_id,
    account_id,
    plan_tier,
    monthly_price,
    start_date,
    end_date,
    is_active
from {{ source('raw', 'raw_billing_subscriptions') }}
