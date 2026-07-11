select
    account_id,
    feature_id,
    event_type,
    total_users,
    active_days,
    features_used,
    last_active_date
from {{ ref('int_product_usage') }}
