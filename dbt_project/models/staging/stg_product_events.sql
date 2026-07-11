select
    event_id,
    account_id,
    feature_id,
    event_type,
    user_count,
    event_date
from {{ source('raw', 'raw_product_events') }}
