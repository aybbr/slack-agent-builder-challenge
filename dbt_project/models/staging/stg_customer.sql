select
    customer_id,
    customer_name,
    industry,
    region
from {{ source('raw', 'raw_customer') }}
