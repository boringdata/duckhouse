{{
  config(
    materialized='external',
    adapter_plugin='flight',
    target='iceberg',
    overrides={
      'table_name': 'concurrent_test'  
    }
  )
}}


-- Create some test data
WITH source_data AS (
    SELECT 1 AS id, 'value_one' AS value
    UNION ALL
    SELECT 2 AS id, 'value_two' AS value
    UNION ALL
    SELECT 3 AS id, 'value_three' AS value
    UNION ALL
    SELECT 4 AS id, 'value_four' AS value
    UNION ALL
    SELECT 5 AS id, 'value_five' AS value
)

-- Apply a simple transformation (filter and add a column)
SELECT 
    id,
    'test_write_' || value AS value
FROM source_data
