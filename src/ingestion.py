"""Stage 1 - ingest the raw CSV with an explicit schema and store it as Parquet (bronze layer)."""
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (DoubleType, IntegerType, StringType, StructField,
                               StructType, TimestampType)

from src import config

RAW_SCHEMA = StructType([
    StructField("Invoice", StringType(), True),
    StructField("StockCode", StringType(), True),
    StructField("Description", StringType(), True),
    StructField("Quantity", IntegerType(), True),
    StructField("InvoiceDate", TimestampType(), True),
    StructField("Price", DoubleType(), True),
    StructField("Customer ID", DoubleType(), True),   # stored as 13085.0 in the Excel export
    StructField("Country", StringType(), True),
])


def read_raw_csv(spark: SparkSession, path=config.RAW_CSV) -> DataFrame:
    df = (spark.read
          .option("header", True)
          .option("multiLine", True)
          .option("escape", '"')
          .option("timestampFormat", "yyyy-MM-dd HH:mm:ss")
          .schema(RAW_SCHEMA)
          .csv(str(path)))
    return (df.withColumn("CustomerID", F.col("Customer ID").cast(IntegerType()))
              .drop("Customer ID"))


def ingest(spark: SparkSession) -> DataFrame:
    df = read_raw_csv(spark)
    df.write.mode("overwrite").parquet(str(config.BRONZE))
    return spark.read.parquet(str(config.BRONZE))
