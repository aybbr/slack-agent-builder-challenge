
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select opportunity_id
from "demo"."main_main"."fct_sales_pipeline"
where opportunity_id is null



  
  
      
    ) dbt_internal_test