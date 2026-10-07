"""Stage 2 - validation and cleaning rules (silver layer) with a data-quality funnel."""
from functools import reduce

import pandas as pd

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from src import config


def is_cancellation(col=None):
    return (F.col("Invoice") if col is None else col).startswith("C")


def is_non_product(col=None):
    code = F.upper(F.trim(F.col("StockCode") if col is None else col))
    by_prefix = reduce(lambda a, b: a | b, [code.startswith(p) for p in config.NON_PRODUCT_PREFIXES])
    return code.isin(config.NON_PRODUCT_CODES) | by_prefix


def remove_reversed_purchases(purchases: DataFrame, cancelled: DataFrame) -> DataFrame:
    """Drop purchase lines that a later cancellation fully reversed (same customer, product and quantity).
    Each cancellation removes only the most recent matching purchase made before it."""
    p = purchases.select("Invoice", "StockCode", "CustomerID", "Quantity",
                         F.col("InvoiceDate").alias("PurchaseDate"))
    c = cancelled.select(F.col("Invoice").alias("CancelInvoice"), "StockCode", "CustomerID",
                         (-F.col("Quantity")).alias("Quantity"), F.col("InvoiceDate").alias("CancelDate"))
    w = Window.partitionBy("CancelInvoice", "StockCode").orderBy(F.desc("PurchaseDate"))
    reversed_lines = (c.join(p, ["CustomerID", "StockCode", "Quantity"])
                       .filter(F.col("PurchaseDate") <= F.col("CancelDate"))
                       .withColumn("rk", F.row_number().over(w)).filter("rk = 1")
                       .select("Invoice", "StockCode", "CustomerID", "Quantity").distinct())
    return purchases.join(reversed_lines, ["Invoice", "StockCode", "CustomerID", "Quantity"], "left_anti")


def clean(df: DataFrame) -> tuple[DataFrame, DataFrame, list[dict]]:
    """Return (clean transactions, cancelled lines, data-quality log)."""
    dq: list[dict] = []

    def step(name: str, frame: DataFrame) -> DataFrame:
        frame = frame.cache()
        dq.append({"step": name, "rows": frame.count()})
        return frame

    df = step("raw", df)
    df = step("customer_id_present", df.filter(F.col("CustomerID").isNotNull()))
    df = df.withColumn("StockCode", F.upper(F.trim("StockCode")))

    cancelled = (df.filter(is_cancellation())
                   .select("Invoice", "StockCode", "Quantity", "InvoiceDate", "Price", "CustomerID")
                   .dropDuplicates())
    df = step("not_cancelled", df.filter(~is_cancellation()))
    df = step("positive_quantity_price", df.filter((F.col("Quantity") > 0) & (F.col("Price") > 0)))
    df = step("product_codes_only", df.filter(~is_non_product()))
    df = step("deduplicated", df.dropDuplicates())
    df = step("reversed_orders_removed", remove_reversed_purchases(df, cancelled))

    df = (df.withColumn("Description", F.trim("Description"))
            .withColumn("Revenue", F.round(F.col("Quantity") * F.col("Price"), 2))
            .withColumn("InvoiceDateOnly", F.to_date("InvoiceDate"))
            .withColumn("InvoiceMonth", F.date_format("InvoiceDate", "yyyy-MM"))
            .withColumn("Year", F.year("InvoiceDate"))
            .withColumn("Month", F.month("InvoiceDate")))
    return df, cancelled, dq


def run(spark: SparkSession, bronze: DataFrame) -> tuple[DataFrame, DataFrame, list[dict]]:
    clean_df, cancelled, dq = clean(bronze)
    clean_df.write.mode("overwrite").partitionBy("Year", "Month").parquet(str(config.SILVER))
    cancelled.write.mode("overwrite").parquet(str(config.SILVER_CANCELLED))
    for row in dq:
        row["removed"] = dq[0]["rows"] - row["rows"]
    pd.DataFrame(dq).to_csv(config.EDA_DIR / "data_quality.csv", index=False)
    return (spark.read.parquet(str(config.SILVER)),
            spark.read.parquet(str(config.SILVER_CANCELLED)), dq)
