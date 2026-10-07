"""Stage 11 - pandas vs PySpark: identical RFM aggregation (read Parquet + group + aggregate) at growing scale.
Best of N runs, wall-clock, same machine."""
import gc
import json
import shutil
import time

import pandas as pd
import psutil
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from src import config

BENCH_DIR = config.OUT / "benchmark"
COLS = ["CustomerID", "Invoice", "InvoiceDate", "Revenue"]


def make_scaled(spark: SparkSession, tx: DataFrame, factor: int) -> str:
    """Replicate the data `factor` times with disjoint customer & invoice ids, written once as Parquet."""
    path = BENCH_DIR / f"scale_{factor}x"
    if not path.exists():
        copies = spark.range(factor).withColumnRenamed("id", "copy")
        (tx.select(*COLS).crossJoin(copies)
           .withColumn("CustomerID", (F.col("CustomerID") + F.col("copy") * 1_000_000).cast("long"))
           .withColumn("Invoice", F.concat_ws("-", "Invoice", "copy"))
           .drop("copy").write.mode("overwrite").parquet(str(path)))
    return str(path)


def rfm_pandas(path: str) -> int:
    df = pd.read_parquet(path, columns=COLS)
    ref = df["InvoiceDate"].max().normalize() + pd.Timedelta(days=1)
    rfm = df.groupby("CustomerID").agg(Last=("InvoiceDate", "max"),
                                       Frequency=("Invoice", "nunique"),
                                       Monetary=("Revenue", "sum"))
    rfm["Recency"] = (ref - rfm["Last"].dt.normalize()).dt.days
    return len(rfm)


def rfm_spark(spark: SparkSession, path: str) -> int:
    """Materialised with the 'noop' sink: a bare count() would let Catalyst prune the aggregates."""
    df = spark.read.parquet(path)
    ref = df.agg(F.date_add(F.to_date(F.max("InvoiceDate")), 1)).first()[0]
    rfm = (df.groupBy("CustomerID")
             .agg(F.max("InvoiceDate").alias("Last"),
                  F.countDistinct("Invoice").alias("Frequency"),
                  F.sum("Revenue").alias("Monetary"))
             .withColumn("Recency", F.datediff(F.lit(ref), F.to_date("Last"))))
    rfm.write.format("noop").mode("overwrite").save()
    return -1  # customer count is taken from the pandas run (same data)


def _timed(fn, *args) -> tuple[float, int]:
    gc.collect()
    t0 = time.perf_counter()
    n = fn(*args)
    return round(time.perf_counter() - t0, 2), n


def run(spark: SparkSession, tx: DataFrame, factors=(1, 5, 10, 20, 40), repeats: int = 3) -> pd.DataFrame:
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for factor in factors:
        path = make_scaled(spark, tx, factor)
        n_rows = spark.read.parquet(path).count()
        rfm_spark(spark, path)  # warm-up: JVM/JIT and file listing
        for engine, fn, args in [("pandas", rfm_pandas, (path,)), ("pyspark", rfm_spark, (spark, path))]:
            times = []
            for _ in range(repeats):
                secs, customers = _timed(fn, *args)
                times.append(secs)
            if customers >= 0:
                n_customers = customers
            rows.append({"scale": f"{factor}x", "rows": n_rows, "engine": engine,
                         "seconds": min(times), "customers": n_customers})
            print(f"    {factor}x {engine}: {min(times)}s ({n_rows:,} rows)")
    result = pd.DataFrame(rows)
    result.to_csv(config.FINAL_DIR / "benchmark.csv", index=False)
    (config.FINAL_DIR / "benchmark_env.json").write_text(json.dumps({
        "cpu_cores": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 1e9, 1),
        "spark_master": config.SPARK_MASTER, "driver_memory": config.SPARK_CONF["spark.driver.memory"]}, indent=2))
    return result


def cleanup() -> None:
    shutil.rmtree(BENCH_DIR, ignore_errors=True)
