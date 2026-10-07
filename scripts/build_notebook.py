"""Generate notebooks/Customer_Segmentation_PySpark.ipynb (the viva walkthrough) from code."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cells = []


def md(text):
    cells.append({"cell_type": "markdown", "id": f"cell-{len(cells):02d}", "metadata": {},
                  "source": text.strip("\n")})


def code(text):
    cells.append({"cell_type": "code", "id": f"cell-{len(cells):02d}", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": text.strip("\n")})


md("""
# Intelligent Online Retail Customer Segmentation & Marketing Recommendation System
### Big Data Analytics mini-project · Apache Spark (PySpark) · UCI Online Retail II

**Business question:** *Who are our customers, how valuable are they, who is at risk of leaving, and what action
should the business take for each customer?*

This notebook walks through the pipeline stage by stage. Every stage calls the same module in `src/` that the
production pipeline (`python -m src.pipeline`) uses.
""")
md("""
## 1. Introduction
An online gift retailer based in the UK records about 1 million invoice lines over two years. The raw
transactions don't tell the business which customers matter, which are slipping away, or how to target each group.

## 2. Problem statement
Turn raw transaction logs into **actionable, per-customer intelligence**:
- a segment
- a value score
- a churn risk
- a recommended marketing action
- product recommendations

The processing has to scale beyond a single machine.

## 3. Objectives
1. Build a scalable ingestion and cleaning pipeline in PySpark, with data-quality tracking.
2. Analyse revenue, products, countries and time trends with Spark SQL.
3. Engineer RFM plus behavioural customer features using aggregations and window functions.
4. Segment customers with MLlib K-Means, choosing K with silhouette analysis.
5. Score customer value and churn risk, then generate rule-based marketing actions.
6. Mine product associations with FP-Growth for cross-sell recommendations.
7. Present the results in a dashboard and business insights.

## 4. Technologies used

| Technology | Purpose |
|---|---|
| PySpark 4 (DataFrame, Spark SQL) | distributed processing |
| Spark MLlib | K-Means, PCA, FP-Growth, StandardScaler |
| Parquet | columnar storage (bronze / silver / gold layers) |
| pandas, Matplotlib, Plotly | reporting |
| Streamlit | dashboard |
""")
md("## 5–7. Libraries and Spark initialisation")
code("""
import sys, json
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

import pandas as pd
from pyspark.sql import functions as F
from IPython.display import Image, display

from src import (config, ingestion, cleaning, eda, features, clustering, profiling, scoring,
                 basket, product_behaviour, recommender, visualization)
from src.pipeline import save_final
from src.spark_session import get_spark

pd.set_option("display.max_columns", 40); pd.set_option("display.width", 200)
spark = get_spark()
print("Spark", spark.version, "| master:", spark.sparkContext.master,
      "| default parallelism:", spark.sparkContext.defaultParallelism)
""")
md("""
## 8. Load the dataset
The dataset is **UCI Online Retail II** (id 502). `scripts/download_data.py` converts its two Excel sheets into one
CSV. Spark then reads that CSV with an **explicit schema**, which is faster and safer than `inferSchema`, and
stores it as Parquet (the *bronze* layer).
""")
code("""
bronze = ingestion.ingest(spark)
bronze.printSchema()
print(f"Raw rows: {bronze.count():,}")
bronze.show(5, truncate=False)
""")
md("## 9. Data understanding")
code("""
bronze.select([F.sum(F.col(c).isNull().cast("int")).alias(c) for c in bronze.columns]).show()
bronze.describe("Quantity", "Price").show()
print("Cancelled invoice lines:", bronze.filter(F.col("Invoice").startswith("C")).count())
""")
md("""
## 10. Data cleaning
| Rule | Why |
|---|---|
| Drop rows with a null `CustomerID` | Customer-level analysis needs to know who bought. |
| Set aside cancellations (`Invoice` starting with `C`) | They become the *cancellation-rate* feature. |
| Keep only `Quantity > 0` and `Price > 0` | Removes returns, adjustments and free items. |
| Drop non-product stock codes (POST, M, BANK CHARGES, AMAZONFEE, TEST…) | These are fees, not purchases. |
| Remove duplicates | Duplicates include the December 2010 rows that appear in both sheets. |

The *silver* layer is Parquet partitioned by `Year` and `Month`.
""")
code("""
tx, cancelled, dq = cleaning.run(spark, bronze)
tx = tx.cache()
pd.DataFrame(dq)
""")
code("""
visualization._style()
visualization.data_quality()
display(Image(str(config.CHARTS_DIR / "00_data_quality_funnel.png")))
""")
md("## 11. Exploratory data analysis (Spark SQL)")
code("""
res = eda.run(spark, tx)
print(eda.QUERIES["monthly_revenue"])
res["kpis"].T
""")
code("""
display(res["by_country"].head(10))
display(res["top_products_revenue"].head(10))
display(res["order_value_distribution"])
""")
code("""
visualization.monthly_revenue(); visualization.top_lists()
for f in ["06_monthly_revenue.png", "07_top_countries.png", "08_top_products.png"]:
    display(Image(str(config.CHARTS_DIR / f)))
""")
md("""
## 12–13. Revenue and customer analysis
`Revenue = Quantity × Price` is added during cleaning. Below is a long-tail check: what share of revenue comes from
the top 20% of customers?
""")
code("""
cust_rev = tx.groupBy("CustomerID").agg(F.sum("Revenue").alias("rev")).toPandas().sort_values("rev", ascending=False)
top20 = cust_rev.head(int(len(cust_rev) * 0.2))["rev"].sum() / cust_rev["rev"].sum()
print(f"Top 20% of customers generate {top20:.1%} of revenue")
""")
md("""
## 14. RFM + behavioural feature engineering
- **Reference date** = last invoice date + 1 day.
- **Recency** = days since the last purchase. **Frequency** = number of distinct invoices. **Monetary** = total
  revenue.
- The behavioural features are: average order value, total items, unique products, average quantity per order,
  active months, tenure, average days between orders (a `lag()` over `Window.partitionBy(CustomerID)`), and
  cancellation rate.
""")
code("""
feats = features.run(spark, tx, cancelled).cache()
print(f"Customers: {feats.count():,}")
feats.select(*config.FEATURE_COLS).summary("min", "25%", "50%", "75%", "max").toPandas()
""")
md("""
## 15. Feature scaling
The RFM values are **heavily right-skewed**: a handful of wholesalers spend over £100k. K-Means uses Euclidean
distance, so we first apply `log1p` to the skewed features and then a `StandardScaler` (mean 0, standard deviation
1). Without this, a few outliers would form their own clusters.
""")
code("""
prep_in = clustering.add_log_features(feats)
print("Model inputs:", clustering.model_input_cols())
""")
md("""
## 16–17. Choosing K and fitting K-Means
We sweep K from 2 to 8 and compute the **silhouette score** (cluster separation) and **WSSSE** (the elbow).
K is chosen as the best silhouette within the range that is actionable for the business (4–6 segments).
""")
code("""
assigned, selection, sweep = clustering.run(feats)
display(sweep)
print(json.dumps(selection, indent=2))
""")
md("## 18. Customer segmentation: naming the clusters from their data")
code("""
segmented, profile = profiling.run(spark, feats, assigned)
profile[["Cluster", "Segment", "Customers", "CustomerShare", "RevenueShare",
         "Recency_median", "Frequency_median", "Monetary_median", "relR", "relF", "relM"]]
""")
md("""
Segments are **not hard-coded**. Each cluster's median recency, frequency and monetary values are compared with
the median over all customers:
- **Recent, frequent and high-spend** clusters become Champions or Loyal.
- **Recent but not yet frequent** clusters become Potential.
- **Not recent but historically frequent or high-spend** clusters become At-Risk or Can't Lose Them.
- **Everything else** becomes Hibernating or Lost.
""")
md("## 19. PCA visualisation")
code("""
print("Explained variance (PC1, PC2):", selection["pca_explained_variance"])
""")
md("## 20. Segment analysis: value score, churn risk, product behaviour")
md("""
**Customer Value Score**
- `CVS = 0.4 × M_pct + 0.3 × F_pct + 0.3 × R_pct`, where each percentile comes from `percent_rank()` over all
  customers. R is inverted so that recent buyers score high.
- Bands: Very High ≥ 80, High ≥ 60, Medium ≥ 40, Low ≥ 20, otherwise Very Low.

**Churn risk** compares inactivity with each customer's *own* buying rhythm:
`OverdueRatio = Recency / max(AvgDaysBetweenOrders, 30)`
- **High**: more than 90 days inactive, and either 2× overdue or high value (CVS ≥ 60).
- **Medium**: more than 90 days inactive, recency above the median, or 1.5× overdue.
- **Low**: everything else.
""")
code("""
scored = scoring.run(segmented).cache()
scored.groupBy("Segment").pivot("ChurnRisk", ["Low", "Medium", "High"]).count().toPandas()
""")
code("""
rules, rules_pdf, basket_meta = basket.run(spark, tx)
print(basket_meta)
rules_pdf[["AntecedentDesc", "ConsequentDesc", "support", "confidence", "lift"]].head(10)
""")
code("""
favourite, pb = product_behaviour.run(tx, scored)
pb["top_products"].groupby("Segment").head(3)
""")
md("## 21. Recommendation engine")
code("""
display(recommender.rules_table())
names = basket.product_names(tx)
final = recommender.run(scored, tx, rules, names, favourite)
ci = save_final(final)
final.select("CustomerID", "Segment", "ValueBand", "ChurnRisk", "Priority", "RecommendedAction",
             "RecommendedProducts").orderBy("Priority", F.desc("CVS")).show(10, truncate=60)
""")
md("## 22. Results and business insights")
code("""
summary = (ci.groupby("Segment")
             .agg(Customers=("CustomerID", "count"), Revenue=("Monetary", "sum"),
                  MedianRecency=("Recency", "median"), MedianOrders=("Frequency", "median"),
                  AvgCVS=("CVS", "mean"), HighRisk=("ChurnRisk", lambda s: (s == "High").mean()))
             .sort_values("Revenue", ascending=False))
summary["RevenueShare"] = summary["Revenue"] / summary["Revenue"].sum()
summary.round(3)
""")
code("""
visualization.make_all()   # regenerate every chart from this run's outputs
for f in ["01_k_selection.png", "02_segment_size_vs_revenue.png", "03_pca_segments.png",
          "05_segment_profile_heatmap.png", "09_cvs_distribution.png", "10_churn_risk_by_segment.png",
          "11_top_association_rules.png", "12_benchmark.png"]:
    p = config.CHARTS_DIR / f
    if p.exists():
        display(Image(str(p)))
""")
md("""
## 23. Conclusion
The pipeline turns about 1M raw transactions into a ranked, per-customer action list:
- a segment
- a value score
- a churn risk
- a prioritised marketing action
- cross-sell products mined with FP-Growth

All of it is computed with Spark DataFrames, Spark SQL and MLlib, so the same code scales from a laptop
(`local[*]`) to a cluster just by changing the Spark master.

**Future scope:**
- streaming ingestion with Structured Streaming
- a supervised churn model once labelled outcomes exist
- product-category enrichment
- A/B testing the recommended campaigns
""")
code("spark.stop()")

nb = {"cells": cells, "metadata": {
    "kernelspec": {"display_name": "Python (BDA Retail)", "language": "python", "name": "bda-retail"},
    "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
out = ROOT / "notebooks" / "Customer_Segmentation_PySpark.ipynb"
out.write_text(json.dumps(nb, indent=1))
print("wrote", out)
