import os
import shutil
import time
import datetime
from typing import Any, Mapping, Optional, Union
from pathlib import Path

import toolz
import pyarrow as pa
import xorq as xo
from xorq.backends.pyiceberg import Backend as PyIcebergBackend

from xorq.flight import FlightServer, FlightUrl
from xorq.common.utils.logging_utils import get_print_logger
from xorq.vendor.ibis.expr import types as ir
from xorq.vendor.ibis.expr import schema as sch

logger = get_print_logger()


class CustomBackend(PyIcebergBackend):
    def __init__(self, warehouse_path=None, **kwargs):
        # Pass warehouse_path explicitly to parent class
        super().__init__(warehouse_path=warehouse_path, **kwargs)
        self.duckdb_path = None
        self.SNAPSHOT_DIR = None
        self.CHECKPOINT_DIR = None
        
        # If warehouse_path was provided during initialization, connect immediately
        if warehouse_path is not None:
            self.do_connect(warehouse_path=warehouse_path, **kwargs)

    def do_connect(
        self, 
        warehouse_path: str,
        duckdb_path: Optional[str] = None,
        snapshot_dir: Optional[str] = None,
        checkpoint_dir: Optional[str] = None,
        namespace: str = "default",
        catalog_name: str = "default",
        catalog_type: str = "sql",
        **kwargs
    ) -> None:
        # Explicitly pass all the required parameters
        super().do_connect(
            warehouse_path=warehouse_path,
            namespace=namespace,
            catalog_name=catalog_name,
            catalog_type=catalog_type,
            **kwargs
        )
        
        self.duckdb_path = duckdb_path or "default_db"
        logger.info(f"Connecting to DuckDB at: {self.duckdb_path}")
        
        self.SNAPSHOT_DIR = Path(snapshot_dir or "snapshots").absolute()
        
        self.SNAPSHOT_DIR.mkdir(exist_ok=True, parents=True)
        
        logger.info(f"Snapshot directory: {self.SNAPSHOT_DIR}")
        
        self.duckdb_con = xo.duckdb.connect(self.duckdb_path)
        self._setup_duckdb_connection()
        self._reflect_views()
    
    def create_table(
        self,
        table_name: str,
        data,
        database: Optional[str] = None,
        overwrite: bool = True,
        target: str =""
    ) -> bool:
        logger.info(f"Inserting data into {table_name}")
        logger.info(f"target: {target}")
        result = super().create_table(table_name, data, database=database, overwrite=overwrite)
        logger.info(f"Data inserted successfully: {result}")
        return result

    def insert(
        self,
        table_name: str,
        data,
        database: Optional[str] = None,
        mode: str = "append",
        target: str =""
    ) -> bool:
        logger.info(f"Inserting data into {table_name}")
        logger.info(f"target: {target}")
        result = super().insert(table_name, data, database, mode)
        logger.info(f"Data inserted successfully: {result}")
        self._create_snapshot_and_export()
        
        return result
    
    def _reflect_views(self):
        table_names = [t[1] for t in self.catalog.list_tables(self.namespace)]

        for table_name in table_names:
            table_path = f"{self.warehouse_path}/{self.namespace}.db/{table_name}"
            self._setup_duckdb_connection()

            escaped_path = table_path.replace("'", "''")
            safe_name = f'"{table_name}"' if "-" in table_name else table_name

            self.duckdb_con.raw_sql(f"""
                CREATE OR REPLACE VIEW {safe_name} AS
                SELECT * FROM iceberg_scan(
                    '{escaped_path}', 
                    version='?',
                    allow_moved_paths=true
                )
            """)
    
    def _setup_duckdb_connection(self):
        """Configure DuckDB connection with required settings"""
        commands = [
            "INSTALL iceberg;",
            "LOAD iceberg;",
            "SET unsafe_enable_version_guessing=true;",
        ]
        for cmd in commands:
            self.duckdb_con.raw_sql(cmd)

    def _create_snapshot_and_export(self) -> None:
        ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
        snap_path = os.path.join(self.SNAPSHOT_DIR, f"{ts}.duckdb")
        
        # Create snapshots of all tables
        for t in self.duckdb_con.tables:
            self.duckdb_con.raw_sql(f"CREATE OR REPLACE TABLE {t}_snapshot as SELECT * FROM {t};")

        # Checkpoint to the configured checkpoint directory
        self.duckdb_con.raw_sql(f"CHECKPOINT {self.duckdb_path}")
        
        # Also copy to snapshots directory
        shutil.copy(self.duckdb_path, snap_path)

        logger.info("Snapshot written to %s", snap_path)
    
    def _get_schema_using_query(self, query: str) -> sch.Schema:
        # only required until github:xorq-labs/xorq #915
        limit_query = f"SELECT * FROM ({query}) AS t LIMIT 0"
        result = self.duckdb_con.sql(limit_query)

        pa_table = result.to_pyarrow()
        return sch.Schema.from_pyarrow(pa_table.schema)
    
    def to_pyarrow_batches(
        self,
        expr: ir.Expr,
        *,
        params: Optional[Mapping[ir.Scalar, Any]] = None,
        limit: Optional[Union[int, str]] = None,
        chunk_size: int = 10_000,
        **_: Any,
    ) -> pa.ipc.RecordBatchReader:
        self._reflect_views()
        return self.duckdb_con.to_pyarrow_batches(
            expr, params=params, limit=limit, chunk_size=chunk_size
        )


def run_server(warehouse_path, port, table_name, duckdb_path=None, snapshot_dir=None, checkpoint_dir=None):
    @toolz.curry
    def custom_connect(
        warehouse_path, 
        duckdb_path=None, 
        snapshot_dir=None, 
        namespace="default", 
        catalog_name="default", 
        catalog_type="sql"
    ):
        def create_backend():
            # Pass warehouse_path during initialization
            backend = CustomBackend(warehouse_path=warehouse_path)
            # Then configure the connection with all parameters
            backend.do_connect(
                warehouse_path=warehouse_path,
                duckdb_path=duckdb_path,
                snapshot_dir=snapshot_dir,
                namespace=namespace,
                catalog_name=catalog_name,
                catalog_type=catalog_type
            )
            return backend
        return create_backend

    server = FlightServer(
        FlightUrl(port=port),
        # Updated to pass all parameters
        connection=custom_connect(
            warehouse_path=warehouse_path, 
            duckdb_path=duckdb_path,
            snapshot_dir=snapshot_dir,
        ),
    )
    server.serve()
    table = pa.Table.from_pylist(
        [
            {"id": 1, "value": "sample_value_1"},
            {"id": 2, "value": "sample_value_2"},
        ],
        schema=pa.schema(
            [
                pa.field("id", pa.int64(), nullable=True),
                pa.field("value", pa.string(), nullable=True),
            ]
        ),
    )
    server.server._conn.create_table(table_name, table, overwrite=True)

    from xorq.flight.client import FlightClient

    flight_client = FlightClient(
            "localhost",
            port
        )

    flight_client.upload_data("my_table", table, target= "duckdb")
    logger.info(f"Uploaded data to grpc://localhost:{port}")

    logger.info(f"Flight server started at grpc://localhost:{port}")
    while server.server is not None:
        time.sleep(1)


def main():
    import argparse
    warehouse_path = "warehouse"
    port = 8816
    table_name = "concurrent_test"
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=(["serve"]))
    parser.add_argument("-w", "--warehouse-path", default=warehouse_path)
    parser.add_argument("-t", "--table-name", default=table_name)
    parser.add_argument("-p", "--port", default=port, type=int)
    parser.add_argument("-d", "--duckdb-path", default=None, 
                        help="Path to DuckDB database file (defaults to warehouse_path/default_db)")
    parser.add_argument("-s", "--snapshot-dir", default=None,
                        help="Directory to store snapshots (defaults to warehouse_path/snapshots)")

    args = parser.parse_args()

    if args.command == "serve":
        run_server(
            args.warehouse_path, 
            args.port, 
            args.table_name, 
            args.duckdb_path,
            args.snapshot_dir,
        )

if __name__ == "__main__":
    main()
