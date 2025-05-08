from xorq.flight.client import FlightClient
import pyarrow.parquet as pq
flight_client = FlightClient(
            host="localhost",
            port=8816
        )

# curl https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2023-01.parquet -o /tmp/yellow_tripdata_2023-01.parquet
arrow_table = pq.read_table("/tmp/yellow_tripdata_2023-01.parquet")

flight_client.upload_data("taxi", arrow_table, target="iceberg")