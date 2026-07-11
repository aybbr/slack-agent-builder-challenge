
  
  create view "demo"."main_staging"."stg_billing_invoices__dbt_tmp" as (
    select
    invoice_id,
    account_id,
    invoice_amount,
    invoice_date,
    paid_date,
    status
from "demo"."main"."raw_billing_invoices"
  );
