
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with child as (
    select opportunity_id as from_field
    from "demo"."main_main"."fct_revenue_recognition"
    where opportunity_id is not null
),

parent as (
    select opportunity_id as to_field
    from "demo"."main_main"."fct_sales_pipeline"
)

select
    from_field

from child
left join parent
    on child.from_field = parent.to_field

where parent.to_field is null



  
  
      
    ) dbt_internal_test