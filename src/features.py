"""Stage 4 - customer-level RFM + behavioural features (gold layer)."""
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from src import config


def build_customer_features(tx: DataFrame, cancelled: DataFrame) -> DataFrame:
    ref_date = tx.agg(F.date_add(F.to_date(F.max("InvoiceDate")), 1).alias("d")).first()["d"]

    # one row per order, so frequency/AOV/gaps are order-level, not line-level
    orders = (tx.groupBy("CustomerID", "Invoice")
                .agg(F.min("InvoiceDate").alias("OrderTime"),
                     F.sum("Revenue").alias("OrderValue"),
                     F.sum("Quantity").alias("OrderQty")))

    # Window + lag: days between consecutive orders of the same customer
    w = Window.partitionBy("CustomerID").orderBy("OrderTime")
    gaps = (orders.withColumn("PrevOrderTime", F.lag("OrderTime").over(w))
                  .withColumn("GapDays", F.datediff("OrderTime", "PrevOrderTime"))
                  .groupBy("CustomerID")
                  .agg(F.avg("GapDays").alias("AvgDaysBetweenOrders")))

    order_stats = (orders.groupBy("CustomerID")
                         .agg(F.countDistinct("Invoice").alias("Frequency"),
                              F.sum("OrderValue").alias("Monetary"),
                              F.avg("OrderValue").alias("AvgOrderValue"),
                              F.avg("OrderQty").alias("AvgQuantityPerOrder"),
                              F.min("OrderTime").alias("FirstPurchase"),
                              F.max("OrderTime").alias("LastPurchase")))

    line_stats = (tx.groupBy("CustomerID")
                    .agg(F.sum("Quantity").alias("TotalItems"),
                         F.countDistinct("StockCode").alias("UniqueProducts"),
                         F.countDistinct("InvoiceMonth").alias("ActiveMonths"),
                         F.mode("Country").alias("Country")))

    cancels = (cancelled.groupBy("CustomerID")
                        .agg(F.countDistinct("Invoice").alias("CancelledOrders")))

    feats = (order_stats.join(line_stats, "CustomerID")
                        .join(gaps, "CustomerID", "left")
                        .join(cancels, "CustomerID", "left")
                        .fillna({"CancelledOrders": 0}))

    return (feats
            .withColumn("Recency", F.datediff(F.lit(ref_date), F.to_date("LastPurchase")))
            .withColumn("TenureDays", F.datediff("LastPurchase", "FirstPurchase"))
            .withColumn("CancellationRate",
                        F.round(F.col("CancelledOrders") / (F.col("Frequency") + F.col("CancelledOrders")), 4))
            .withColumn("IsUK", (F.col("Country") == "United Kingdom").cast("int"))
            .withColumn("Monetary", F.round("Monetary", 2))
            .withColumn("AvgOrderValue", F.round("AvgOrderValue", 2))
            .withColumn("AvgQuantityPerOrder", F.round("AvgQuantityPerOrder", 2))
            .withColumn("AvgDaysBetweenOrders", F.round("AvgDaysBetweenOrders", 1))
            .withColumn("ReferenceDate", F.lit(ref_date))
            .select("CustomerID", "Country", "IsUK", *config.FEATURE_COLS, "CancelledOrders",
                    "FirstPurchase", "LastPurchase", "ReferenceDate"))


def run(spark: SparkSession, tx: DataFrame, cancelled: DataFrame) -> DataFrame:
    feats = build_customer_features(tx, cancelled)
    feats.write.mode("overwrite").parquet(str(config.GOLD_FEATURES))
    return spark.read.parquet(str(config.GOLD_FEATURES))
