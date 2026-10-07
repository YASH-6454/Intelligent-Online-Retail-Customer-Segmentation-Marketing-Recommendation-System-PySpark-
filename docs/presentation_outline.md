# Presentation outline (about 15 slides, 12–15 minutes)

Chart paths are relative to `outputs/charts/`.

| # | Slide | Content | Visual |
|---|---|---|---|
| 1 | **Title** | Intelligent Online Retail Customer Segmentation & Marketing Recommendation System Using PySpark. Team names, guide, date. | — |
| 2 | **The business problem** | "1.07M transactions, but which customers matter, who is leaving, and what do we do?" The top 20% of customers make 76.6% of revenue. | One large number: 76.6% |
| 3 | **Objectives** | Scalable cleaning → analytics → segmentation → value & churn → actions → cross-sell. | 6 icons |
| 4 | **Dataset** | UCI Online Retail II: 1,067,371 rows, Dec 2009 – Dec 2011, 41 countries, 8 columns. | Column table |
| 5 | **Architecture** | Bronze/silver/gold Parquet → Spark SQL → features → MLlib → engine → dashboard. | README diagram |
| 6 | **Data cleaning** | 6 rules: 1.07M → 770K rows. Highlight the reversed-order catch (80,995-unit order cancelled 12 minutes later). | `00_data_quality_funnel.png` |
| 7 | **EDA** | UK is 83.5% of revenue. November peak (£1.12M). Top products. AOV £453. | `06_monthly_revenue.png`, `08_top_products.png` |
| 8 | **Feature engineering** | RFM plus 8 behavioural features. Window `lag()` for gaps between orders. | Feature table |
| 9 | **Choosing K** | Silhouette and elbow. Why K=5, not K=2 or K=4: distinct actionable groups. | `01_k_selection.png` |
| 10 | **Segments** | 5 segments. Champions are 17.6% of customers and 71.8% of revenue. | `02_segment_size_vs_revenue.png`, `05_segment_profile_heatmap.png` |
| 11 | **Segments in PCA space** | 73.9% of variance in 2 components. | `03_pca_segments.png` |
| 12 | **Value & churn** | CVS formula and churn rules. 309 valuable-and-slipping customers holding £1.42M. At-Risk customers have a 41% cancellation rate. | `10_churn_risk_by_segment.png`, `09_cvs_distribution.png` |
| 13 | **Market basket** | 144 FP-Growth rules. "Complete the set" (teacups, signs, lunch boxes) with lift up to 32. 78% of customers get product recommendations. | `11_top_association_rules.png` |
| 14 | **Live demo** | Streamlit: Overview → Segments → Customer search (a P1 customer) → Action list download. | Dashboard |
| 15 | **Why Spark: the benchmark** | pandas wins below about 8M rows; PySpark wins from about 15M; Spark scales out. | `12_benchmark.png` |
| 16 | **Business recommendations** | The 7 insights from report Chapter 6. | Bullets |
| 17 | **Conclusion & future scope** | Supervised churn model, Structured Streaming, ALS, A/B testing. | — |

**Demo script (2 minutes)**
1. `streamlit run app/streamlit_app.py`
2. On Overview, point out the KPIs and the "revenue at risk" tile.
3. On Segments, pick At-Risk and show its top products and churn mix.
4. On Customer search, enter the first P1 customer from the Action list. It shows the segment, value, risk,
   recommended action and "frequently bought together" products.
5. On Action list, filter to P1 and download the CSV: "this goes to the marketing team on Monday."

See `docs/viva_qa.md` for likely questions.
