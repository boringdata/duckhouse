from typing import Any, Dict 

import xorq as xo
from xorq.flight.client import FlightClient

from dbt.adapters.duckdb.plugins import BasePlugin
from dbt.adapters.duckdb.utils import SourceConfig
from dbt.adapters.duckdb.utils import TargetConfig
from dbt.adapters.events.logging import AdapterLogger

logger = AdapterLogger("xorq-flight")


def get_table_schema(client, key):
     result = client.do_action_one("get_schema_using_query", f"select * from {key}")
     return result if result else None


class Plugin(BasePlugin):
    """
    An experimental dbt-duckdb plugin for connecting to Flight servers with Iceberg tables.
    """
    
    def initialize(self, plugin_config: Dict[str, Any]):
        self._config = plugin_config
        self._client = FlightClient(
            host=self._config["host"],
            port=self._config["port"],
        )
        logger.info(f"Connected to Flight server at {self._config['host']}:{self._config['port']}")

    def load(self, source_config: SourceConfig):
        table_name = source_config.identifier
        logger.info(f"Loading data from Flight: {table_name}")
        schema = get_table_schema(self._client, f"{table_name}")
        table_ref = xo.table(name=table_name, schema=schema)
        logger.info(f"table_ref: {table_name}")
        result = self._client.execute(table_ref.as_table())
        
        return result


    def store(self, target_config: TargetConfig):
        logger.info("inside store")
        
        table_name = target_config.relation.identifier
        if hasattr(target_config, 'config') and target_config.config:
            overrides = target_config.config.get('overrides', {})
            if 'table_name' in overrides:
                table_name = overrides['table_name']

            target = target_config.config.get('target')
        
        logger.info(f"Storing data to Flight: {table_name}")
        logger.info(f"Using target: {target}")
        
        from dbt.adapters.duckdb.plugins import pd_utils
        df = pd_utils.target_to_df(target_config)
        
        import pyarrow as pa
        arrow_table = pa.Table.from_pandas(df)
        
        self._client.upload_data(table_name, arrow_table, target=target)
        logger.info(f"Successfully uploaded {len(df)} rows to {table_name}")

    def default_materialization(self):
        return "table"
