"""Stage 9 - what each segment buys: top products and keyword-based categories."""
import pandas as pd
from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

from src import config


def category_expr(desc: Column | None = None) -> Column:
    """Heuristic category from the product description (first keyword group that matches a word start)."""
    d = F.upper(F.coalesce(F.col("Description") if desc is None else desc, F.lit("")))
    expr = None
    for category, words in config.CATEGORY_KEYWORDS:
        cond = d.rlike(r"\b(" + "|".join(words) + ")")
        expr = F.when(cond, category) if expr is None else expr.when(cond, category)
    return expr.otherwise(config.DEFAULT_CATEGORY)


def with_category(tx: DataFrame) -> DataFrame:
    return tx.withColumn("Category", category_expr())


def run(tx: DataFrame, segments: DataFrame, top_n: int = 10) -> tuple[DataFrame, dict]:
    """segments: CustomerID, Segment. Returns (favourite category per customer, pandas outputs)."""
    seg_tx = with_category(tx).join(segments.select("CustomerID", "Segment"), "CustomerID")

    by_product = (seg_tx.groupBy("Segment", "StockCode")
                        .agg(F.mode("Description").alias("Description"),
                             F.sum("Quantity").alias("Quantity"),
                             F.round(F.sum("Revenue"), 2).alias("Revenue"),
                             F.countDistinct("CustomerID").alias("Buyers")))
    w = Window.partitionBy("Segment").orderBy(F.desc("Revenue"))
    top_products = (by_product.withColumn("Rank", F.row_number().over(w))
                              .filter(F.col("Rank") <= top_n).orderBy("Segment", "Rank").toPandas())

    seg_rev = seg_tx.groupBy("Segment").agg(F.sum("Revenue").alias("SegRevenue"))
    category_mix = (seg_tx.groupBy("Segment", "Category").agg(F.sum("Revenue").alias("Revenue"))
                          .join(seg_rev, "Segment")
                          .withColumn("Share", F.round(F.col("Revenue") / F.col("SegRevenue"), 4))
                          .drop("SegRevenue").orderBy("Segment", F.desc("Share")).toPandas())

    wc = Window.partitionBy("CustomerID").orderBy(F.desc("Revenue"))
    favourite = (with_category(tx).groupBy("CustomerID", "Category").agg(F.sum("Revenue").alias("Revenue"))
                 .withColumn("rk", F.row_number().over(wc)).filter("rk = 1")
                 .select("CustomerID", F.col("Category").alias("FavouriteCategory")))

    top_products.to_csv(config.FINAL_DIR / "segment_top_products.csv", index=False)
    category_mix.to_csv(config.FINAL_DIR / "segment_category_mix.csv", index=False)
    return favourite, {"top_products": top_products, "category_mix": category_mix}


def category_coverage(tx: DataFrame) -> pd.DataFrame:
    """Share of revenue that landed in each category (used to report how good the heuristic is)."""
    return (with_category(tx).groupBy("Category").agg(F.round(F.sum("Revenue"), 2).alias("Revenue"))
            .orderBy(F.desc("Revenue")).toPandas())
