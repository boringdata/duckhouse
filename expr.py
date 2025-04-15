import xorq as xo
import xorq.expr.datatypes as dt

from xorq.caching import SourceStorage


@xo.udf.make_pandas_udf(
    schema=xo.schema({"L_EXTENDEDPRICE": float, "L_DISCOUNT": float}),
    return_type=dt.float,
    name="calculate_discount_value"
)
def calculate_discount_value(df):
    return df["L_EXTENDEDPRICE"] * df["L_DISCOUNT"]

snow = xo.snowflake.connect_env(schema="TPCH_SF1")
duckdb_con = xo.duckdb.connect()

storage = SourceStorage(duckdb_con)

expr = (
    snow.table("LINEITEM")
    .select(
        xo._.L_QUANTITY.cast(float).name("L_QUANTITY"),
        xo._.L_EXTENDEDPRICE.cast(float).name("L_EXTENDEDPRICE"),
        xo._.L_DISCOUNT.cast(float).name("L_DISCOUNT"),
        xo._.L_ORDERKEY
    )
    .into_backend(xo.connect())
    .mutate(discount_value=calculate_discount_value.on_expr)
    .group_by(xo._.L_ORDERKEY)
    .agg(
        xo._.discount_value.sum().name("total_discount"),
        xo._.L_QUANTITY.sum().name("total_quantity")
    )
    .cache(storage=storage)
)
