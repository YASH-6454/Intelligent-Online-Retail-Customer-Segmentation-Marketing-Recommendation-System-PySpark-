# Intelligent Online Retail Customer Segmentation & Marketing Recommendation System (PySpark)

> **Business question:** who are our customers, how valuable are they, who is about to leave, and what should
> the business do for each one?

The system takes about 1 million raw transactions from the **UCI Online Retail II** dataset. It is a UK online gift
retailer, with data from Dec 2009 to Dec 2011. It turns those transactions into a per-customer table with these
columns:

| Customer | Segment | Value (0–100) | Churn risk | Priority | Recommended action | Recommended products |
|---|---|---|---|---|---|---|

Everything is built on **Apache Spark** and uses these features:

- DataFrames, Spark SQL and window functions
- Parquet bronze/silver/gold layers
- MLlib: VectorAssembler, StandardScaler, K-Means, ClusteringEvaluator, PCA and FP-Growth

A Streamlit dashboard sits on top for business users.

## Architecture

```
 online_retail_II.xlsx ──► CSV ──► [1] Ingestion (explicit schema) ──► bronze/ (Parquet)
                                        │
                                   [2] Cleaning & validation ──► silver/ (Parquet, partitioned Year/Month)
                                        │                          + data-quality funnel
                     ┌──────────────────┼───────────────────────┐
                [3] EDA (Spark SQL)  [4] Features (gold/)     [8] FP-Growth market basket
                                        │ RFM + 8 behavioural   │  association rules
                                   [5] log1p → scale → K-Means  │
                                        │  K sweep, silhouette  │
                                   [6] Profiling → named segments
                                        │                       │
                                   [7] Value score + churn risk │
                                        │                       │
                [9] Product behaviour ─►[10] Rule-based recommendation engine ◄─┘
                                        │
                     outputs/final/customer_intelligence.parquet
                                        │
                     [12] Charts (PNG)   ·   Streamlit dashboard   ·   Notebook   ·   Report
```

## Quick start (macOS)

```bash
./scripts/setup_env.sh                       # Java 21 + Python 3.12 venv + dependencies + Spark smoke test
source .venv/bin/activate
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home

python scripts/download_data.py              # downloads + converts the dataset (~1 min)
python -m src.pipeline                       # full pipeline (~3-6 min); --skip-benchmark to go faster
pytest -q                                    # unit tests on tiny synthetic data
streamlit run app/streamlit_app.py           # dashboard at http://localhost:8501
jupyter notebook notebooks/Customer_Segmentation_PySpark.ipynb
```

Spark 4 needs **Java 17 or 21**. `src/spark_session.py` points `JAVA_HOME` at Homebrew's openjdk@21
automatically if `JAVA_HOME` isn't set.

## Project layout

| Path | What it does |
|---|---|
| `src/config.py` | All paths, Spark settings and **every threshold** (churn days, value bands, K range, FP-Growth support) |
| `src/ingestion.py` | Explicit `StructType` schema, CSV → Parquet |
| `src/cleaning.py` | 5 validation rules with a row-count funnel; cancellations are kept aside for a feature |
| `src/eda.py` | 9 Spark SQL queries (KPIs, countries, products, monthly trend with running total, …) |
| `src/features.py` | Recency, Frequency, Monetary, AOV, items, unique products, avg qty, active months, tenure, avg days between orders (`lag` window), cancellation rate |
| `src/clustering.py` | log1p → VectorAssembler → StandardScaler → K-Means for K = 2..8, silhouette + elbow, PCA |
| `src/profiling.py` | Names each cluster from its median R/F/M against the overall medians (no hard-coded cluster ids) |
| `src/scoring.py` | Customer Value Score = 0.4·M + 0.3·F + 0.3·R percentiles; churn risk from inactivity and each customer's own purchase rhythm |
| `src/basket.py` | FP-Growth on invoice baskets; the support level is tuned automatically to give 100–500 rules |
| `src/product_behaviour.py` | Top products per segment, keyword-based category mix, each customer's favourite category |
| `src/recommender.py` | Ordered rule table → action / channel / offer / priority, plus the top 3 "frequently bought together" products the customer doesn't already own |
| `src/benchmark.py` | The same RFM aggregation in pandas and PySpark at 1×, 5× and 10× data |
| `src/visualization.py` | 13 report charts → `outputs/charts/` |
| `src/pipeline.py` | Runs every stage: `python -m src.pipeline` |
| `app/streamlit_app.py` | Dashboard with 6 pages: Overview, Segments, Customer search, Market basket, Model & data quality, Action list |
| `notebooks/` | A walkthrough notebook for the viva |
| `docs/report.md`, `docs/presentation_outline.md` | Report chapters and the slide deck outline |

## Key outputs

- `outputs/final/customer_intelligence.csv` has one row per customer, with segment, scores, action and product recommendations.
- `outputs/final/segment_profiles.csv` holds the per-segment statistics and the share of customers and revenue.
- `outputs/final/association_rules.csv` holds the market-basket rules with support, confidence and lift.
- `outputs/final/run_summary.json` holds the headline numbers from the last run.
- `outputs/charts/*.png` holds the figures for the report.
