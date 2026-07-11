select
    subscription_id,
    account_id,
    plan_tier,
    monthly_price,
    start_date,
    end_date,
    is_active
from "demo"."main"."raw_billing_subscriptions"