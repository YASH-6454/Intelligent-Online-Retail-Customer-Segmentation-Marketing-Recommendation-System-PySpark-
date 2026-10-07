"""End-to-end orchestrator:  python -m src.pipeline [--skip-benchmark] [--k K]"""
import argparse
import json
import time

from pyspark.sql import functions as F

from src import (basket, benchmark, cleaning, clustering, config, eda, features, ingestion,
                 product_behaviour, profiling, recommender, scoring, visualization)
from src.spark_session import get_spark

FINAL_COLUMNS = [
    "CustomerID", "Country", "Segment", "SegmentGroup", "Cluster", "CVS", "ValueBand", "ChurnRisk",
    "ChurnScore", "OverdueRatio", "Priority", "RuleId", "RecommendedAction", "Channel", "OfferType",
    "RecommendedProducts", "FavouriteCategory", "ServiceFlag", "R_Score", "F_Score", "M_Score",
    *config.FEATURE_COLS, "CancelledOrders", "FirstPurchase", "LastPurchase", "PC1", "PC2",
]


def save_final(final) -> "pd.DataFrame":
    """Select, order and persist the per-customer intelligence table (Parquet + CSV)."""
    final = final.select(*FINAL_COLUMNS).orderBy("Priority", F.desc("CVS")).cache()
    final.write.mode("overwrite").parquet(str(config.FINAL_DIR / "customer_intelligence.parquet"))
    pdf = final.toPandas()
    pdf.to_csv(config.FINAL_DIR / "customer_intelligence.csv", index=False)
    return pdf


class Stage:
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        print(f"\n[{self.name}]")
        self.t0 = time.perf_counter()

    def __exit__(self, *exc):
        print(f"  done in {time.perf_counter() - self.t0:.1f}s")


def main(skip_benchmark: bool = False, k: int | None = None) -> dict:
    spark = get_spark()
    print(f"Spark {spark.version} | master={spark.sparkContext.master}")
    summary = {}

    with Stage("1. Ingestion (CSV -> bronze Parquet)"):
        bronze = ingestion.ingest(spark)
    with Stage("2. Cleaning & validation (silver)"):
        tx, cancelled, dq = cleaning.run(spark, bronze)
        tx = tx.cache()
        for row in dq:
            print(f"  {row['step']:<26}{row['rows']:>12,}")
        summary["data_quality"] = dq
    with Stage("3. EDA with Spark SQL"):
        summary["kpis"] = eda.run(spark, tx)["kpis"].iloc[0].to_dict()
    with Stage("4. Feature engineering (gold)"):
        feats = features.run(spark, tx, cancelled).cache()
        print(f"  customers: {feats.count():,}")
    with Stage("5. K-Means clustering"):
        assigned, selection, _ = clustering.run(feats, k=k)
        summary["k_selection"] = selection
        print(f"  {selection['reason']}")
    with Stage("6. Segment profiling"):
        segmented, profile = profiling.run(spark, feats, assigned)
        print(profile[["Cluster", "Segment", "Customers", "Recency_median", "Frequency_median",
                       "Monetary_median", "RevenueShare"]].to_string(index=False))
    with Stage("7. Value score & churn risk"):
        scored = scoring.run(segmented).cache()
    with Stage("8. Market basket (FP-Growth)"):
        rules, rules_pdf, basket_meta = basket.run(spark, tx)
        summary["basket"] = basket_meta
    with Stage("9. Product behaviour per segment"):
        favourite, _ = product_behaviour.run(tx, scored)
        product_behaviour.category_coverage(tx).to_csv(config.FINAL_DIR / "category_coverage.csv", index=False)
    with Stage("10. Recommendation engine"):
        names = basket.product_names(tx)
        pdf = save_final(recommender.run(scored, tx, rules, names, favourite))
        summary["final_customers"] = len(pdf)
        summary["segments"] = pdf["Segment"].value_counts().to_dict()
        summary["churn_risk"] = pdf["ChurnRisk"].value_counts().to_dict()
        summary["priority"] = pdf["Priority"].value_counts().to_dict()
        summary["with_product_recs"] = int(pdf["RecommendedProducts"].notna().sum())
    if not skip_benchmark:
        with Stage("11. Benchmark pandas vs PySpark"):
            benchmark.run(spark, tx)
            benchmark.cleanup()
    with Stage("12. Charts"):
        visualization.make_all()

    (config.FINAL_DIR / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nOutputs in {config.OUT}")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-benchmark", action="store_true")
    ap.add_argument("--k", type=int, default=None, help="force a K instead of the silhouette choice")
    args = ap.parse_args()
    main(skip_benchmark=args.skip_benchmark, k=args.k)
