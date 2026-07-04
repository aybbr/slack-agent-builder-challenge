select
    customer_id,
    customer_name,
    industry,
    region
from {{ ref('stg_customer') }}
