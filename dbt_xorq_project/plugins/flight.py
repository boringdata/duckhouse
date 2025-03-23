from typing import Any, Dict 

from xorq.flight.client import FlightClient

from dbt.adapters.duckdb.plugins import BasePlugin
from dbt.adapters.duckdb.utils import SourceConfig
from dbt.adapters.duckdb.utils import TargetConfig
from dbt.adapters.events.logging import AdapterLogger

logger = AdapterLogger("DuckDB")


class Plugin(BasePlugin):
    """
    An experimental dbt-duckdb plugin for connecting to Flight servers with Iceberg tables.
    """
    
    def initialize(self, plugin_config: Dict[str, Any]):
        self._config = plugin_config
        try:
            self._client = FlightClient(
                host=self._config["host"],
                port=self._config["port"],
            )
            logger.info(f"Connected to Flight server at {self._config['host']}:{self._config['port']}")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Flight server: {e}")

    def load(self, source_config: SourceConfig):
        table_name = source_config.identifier
        logger.info(f"Loading data from Iceberg table: {table_name}")
        
        try:
            import xorq as xo
            import pyarrow as pa
            # TODO: avoid hardcoding and interop with sources.yml
            schema=pa.schema(
                [
                    pa.field("id", pa.int64(), nullable=True),
                    pa.field("value", pa.string(), nullable=True),
                ]
            )
            
            table_ref = xo.table(name=table_name, schema=schema)
            logger.info(f"table_ref: {table_name}")

            result = self._client.execute_query(table_ref.as_table())
            
            return result
        except Exception as e:
            logger.error(f"Error loading data from Flight server: {e}")
            raise RuntimeError(f"Failed to load data from Flight server: {e}")


    def store(self, target_config: TargetConfig):
        try:
            logger.info("inside store")
            
            table_name = target_config.relation.identifier
            if hasattr(target_config, 'config') and target_config.config:
                overrides = target_config.config.get('overrides', {})
                if 'table_name' in overrides:
                    table_name = overrides['table_name']
            
            logger.info(f"Storing data to Iceberg table: {table_name}")
            
            from dbt.adapters.duckdb.plugins import pd_utils
            df = pd_utils.target_to_df(target_config)
            
            if df.empty:
                logger.warning(f"No data to store in table {table_name}")
                return
            
            import pyarrow as pa
            arrow_table = pa.Table.from_pandas(df)
            
            self._client.upload_data(table_name, arrow_table)
            logger.info(f"Successfully uploaded {len(df)} rows to {table_name}")
                
        except Exception as e:
            logger.error(f"Error storing data to Iceberg table {table_name}: {e}")
            raise RuntimeError(f"Failed to store data to Iceberg table {table_name}: {e}")

    def default_materialization(self):
        return "table"
