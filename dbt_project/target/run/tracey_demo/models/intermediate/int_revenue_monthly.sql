
  
  create view "demo"."main_intermediate"."int_revenue_monthly__dbt_tmp" as (
    select
    i.account_id,
    s.plan_tier,
    sum(i.invoice_amount) as total_revenue,
    count(distinct i.invoice_id) as invoice_count,
    count(distinct case when i.status = 'paid' then i.invoice_id end) as paid_invoices,
    date_trunc('month', i.invoice_date) as revenue_month
from "demo"."main_staging"."stg_billing_invoices" i
left join "demo"."main_staging"."stg_billing_subscriptions" s
    on i.account_id = s.account_id
group by i.account_id, s.plan_tier, date_trunc('month', i.invoice_date)
  );
