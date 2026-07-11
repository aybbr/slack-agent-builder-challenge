select
    invoice_id,
    account_id,
    invoice_amount,
    invoice_date,
    paid_date,
    status
from {{ source('raw', 'raw_billing_invoices') }}
