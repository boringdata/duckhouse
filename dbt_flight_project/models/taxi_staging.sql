{{ config(
    materialized='external',
    plugin='flight',
    target='iceberg'
) }}

SELECT 
    *
FROM {{ source('xorq_flight', 'taxi') }}
QUALIFY row_number() over (partition by VendorID, tpep_pickup_datetime) = 1