
    
    

select
    opportunity_id as unique_field,
    count(*) as n_records

from "demo"."main_staging"."stg_sf_opportunities"
where opportunity_id is not null
group by opportunity_id
having count(*) > 1


