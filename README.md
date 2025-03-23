# Multi-Engine: `dbt-duckdb` -> `xo.FlightServer` -> `duckdb` -> `pyiceberg`

This plugin integrates dbt-duckdb with xorq to define Flight services for
Iceberg and DuckDB. It enables dbt models to read from and write to Iceberg
tables through a Flight server.

## Run

```
cd dbt_xorq_project
export PYTHONPATH="$PWD:$PYTHONPATH"
dbt run
```

## Configuration

### Profile Configuration

In your `profiles.yml` file, configure dbt to use the Flight plugin:

```yaml
dbt_xorq:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: ":memory:"
      plugins:
        - module: plugins.flight 
          config:
            host: localhost
            port: 8816
      threads: 1
```
## Prerequisites

Before using this plugin, you need:

1. A running xorq Flight server with configured Iceberg catalog
2. The xorq Python package installed (`pip install xorq`)
3. PyArrow installed (`pip install pyarrow`)

## Running the Flight Server

You can run the Flight server using the provided script:

```bash
python iceberg_over_flight.py serve -w warehouse -p 8816
```

## Supported Operations

[x] Test reading from Iceberg tables via sources with fixed schema
[ ] Writing to Iceberg tables via materialized models
[ ] Filtering and column selection
