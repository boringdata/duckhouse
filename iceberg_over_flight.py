import os
import shutil
import time
from datetime import datetime
from typing import Optional

from pathlib import Path

import toolz
import pyarrow as pa
import xorq as xo
from xorq.backends.pyiceberg import Backend as PyIcebergBackend

from xorq.flight import FlightServer, FlightUrl
from xorq.common.utils.logging_utils import get_print_logger

logger= get_print_logger()


class CustomBackend(PyIcebergBackend):
    def __init__(self):
         super().__init__()
         self.SNAPSHOT_DIR = Path("snapshots").absolute()
         Path(self.SNAPSHOT_DIR).mkdir(exist_ok=True)

    def do_connect(
        self, 
        **kwargs
    ) -> None:
        super().do_connect(**kwargs)

        self.duckdb_con = xo.duckdb.connect("default_db")
        self._setup_duckdb_connection()
        self._reflect_views()

    def insert(
         self,
         table_name: str,
         data,
         database: Optional[str] = None,
         mode: str = "append",
     ) -> bool:
         logger.info(f"Inserting data into {table_name}")
         result = super().insert(table_name, data, database, mode)
         logger.info(f"Data inserted successfully: {result}")
         self._create_snapshot_and_export()
         
         return result

    def _create_snapshot_and_export(self) -> None:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        snap_path = os.path.join(self.SNAPSHOT_DIR, f"{ts}.duckdb")
        
        for t in self.duckdb_con.tables:
            self.duckdb_con.raw_sql(f"CREATE OR REPLACE TABLE {t}_snapshot as SELECT * FROM {t};")

        self.duckdb_con.raw_sql("CHECKPOINT default_db")
        shutil.copy("default_db", snap_path)

        logger.info("Snapshot written to %s (copied from %s)", snap_path, "default_db")


def run_server(warehouse_path, port, table_name):
    @toolz.curry
    def custom_connect(warehouse_path, namespace="default", catalog_name="default", catalog_type="sql"):
        def create_backend():
            backend = CustomBackend()
            backend.do_connect(warehouse_path=warehouse_path)
            return backend
        return create_backend

    server = FlightServer(
        FlightUrl(port=port),
        # connection=xo.pyiceberg.connect,
        # connection = partial(xo.duckdb.connect, f"{warehouse_path}.db")
        connection= custom_connect(warehouse_path),
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
    parser.add_argument("-t", "--table-name", default = table_name)
    parser.add_argument("-p", "--port", default=port, type=int)

    args = parser.parse_args()

    if args.command == "serve":
        run_server(args.warehouse_path, args.port, args.table_name)

if __name__ == "__main__":
    main()
