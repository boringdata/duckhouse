{{ config(
    materialized='external',
    plugin='flight',
    target='duckdb'
) }}

SELECT 
    VendorID,
    count(*) as count
FROM {{ ref('taxi_staging') }}
group by VendorID