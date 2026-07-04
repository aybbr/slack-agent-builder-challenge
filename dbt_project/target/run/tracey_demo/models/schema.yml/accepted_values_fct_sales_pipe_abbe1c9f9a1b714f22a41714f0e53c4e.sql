
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        stage as value_field,
        count(*) as n_records

    from "demo"."main_main"."fct_sales_pipeline"
    group by stage

)

select *
from all_values
where value_field not in (
    'prospecting','qualification','proposal','negotiation','closed_won','closed_lost'
)



  
  
      
    ) dbt_internal_test