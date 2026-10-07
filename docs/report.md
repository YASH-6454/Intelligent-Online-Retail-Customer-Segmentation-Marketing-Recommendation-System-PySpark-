# Intelligent Online Retail Customer Segmentation and Marketing Recommendation System Using PySpark

*Big Data Analytics project report.* All quantitative metrics come from the pipeline run in `outputs/`.
Figures are in `outputs/charts/` and high-resolution Streamlit UI screens are in `docs/images/dashboard/`.
**Full Word Document (.docx):** Available at [docs/project_report.docx](file:///Users/rohit/Desktop/BDA%20project/docs/project_report.docx) (generated via `python scripts/generate_docx_report.py`).

---

## Chapter 1: Introduction

### 1.1 Background
Online retailers collect large transaction logs: every invoice line records who bought what, when, and for how
much. That raw log doesn't answer the questions marketing teams actually ask:
- Which customers are most valuable?
- Who is drifting away?
- What offer should each customer receive?

### 1.2 Problem statement
A UK online gift retailer has about 1.07 million invoice lines from 2009–2011, but no view of customer value,
churn risk or targeting. The task is to convert those transactions into **actionable per-customer intelligence**,
using a pipeline that scales beyond one machine.

### 1.3 Objectives
1. Ingest, validate and clean the transaction data with PySpark, tracking data quality at every step.
2. Analyse revenue, product, country and time trends using Spark SQL.
3. Engineer RFM and behavioural customer features using distributed aggregations and window functions.
4. Segment customers with MLlib K-Means, choosing K with a documented and reproducible criterion.
5. Score customer value (0–100) and churn risk, and assign a prioritised marketing action to every customer.
6. Mine frequently-bought-together products with FP-Growth for personalised cross-sell.
7. Present the results in a dashboard, a notebook and business recommendations.

### 1.4 Motivation
In this dataset the **top 20% of customers generate 76.6% of revenue**. Retaining the right customers matters far
more than treating everyone the same.

---

## Chapter 2: Existing system and proposed system

### 2.1 Traditional approach
- Spreadsheet RFM scoring (quintiles 1–5) or a single K-Means run on three RFM columns in pandas.

### 2.2 Limitations
- Single-machine memory limits.
- Arbitrary cluster labels ("cluster 0, 1, 2").
- No link from segments to concrete actions.
- No churn view.
- K is often fixed without justification.
- Data-quality problems hidden in the data, such as reversed orders, inflate customer value.

### 2.3 Proposed system
An end-to-end Spark pipeline:

> bronze → silver → gold Parquet layers → Spark SQL analytics → RFM plus 8 behavioural features → log-scaled
> K-Means with an interpretability-aware K choice → automatic segment naming → value score and churn risk →
> FP-Growth rules → a rule-based recommendation engine → Streamlit dashboard

---

## Chapter 3: Methodology

### 3.1 Dataset
**UCI Online Retail II** (id 502): 1,067,371 rows, 1 Dec 2009 – 9 Dec 2011, 41 countries.

| Column | Meaning |
|---|---|
| Invoice | Invoice number. A leading `C` means a cancellation. |
| StockCode | Product code |
| Description | Product name |
| Quantity | Units bought |
| InvoiceDate | Date and time of the invoice |
| Price | Unit price (£) |
| Customer ID | Customer identifier |
| Country | Customer's country |

### 3.2 Technology
| Technology | Use |
|---|---|
| PySpark 4.2 (DataFrame API, Spark SQL) | All data processing |
| Spark MLlib | VectorAssembler, StandardScaler, KMeans, ClusteringEvaluator, PCA, FPGrowth |
| Parquet | Storage, partitioned by Year and Month |
| pandas and Matplotlib | Report outputs |
| Plotly and Streamlit | Dashboard |
| pytest | 10 unit tests |
| Environment | Java 21, Python 3.12, `local[*]` on a 10-core / 16 GB laptop |

### 3.3 RFM and behavioural features
The reference date is the last invoice date + 1 day (10 Dec 2011).

| Feature | Definition |
|---|---|
| Recency | Days since last purchase |
| Frequency | Distinct invoices |
| Monetary | Total revenue (£) |
| AvgOrderValue | Monetary / Frequency |
| TotalItems | Units bought |
| UniqueProducts | Distinct StockCodes |
| AvgQuantityPerOrder | Units per invoice |
| ActiveMonths | Distinct months with a purchase |
| TenureDays | First to last purchase |
| AvgDaysBetweenOrders | Mean gap between consecutive orders (`lag` over a customer window) |
| CancellationRate | Cancelled invoices / all invoices |

### 3.4 Clustering
- Seven features go into the model: Recency, Frequency, Monetary, AOV, UniqueProducts, ActiveMonths and
  CancellationRate.
- `log1p` is applied to the six skewed ones, then StandardScaler (mean 0, standard deviation 1), then K-Means
  (seed 42).
- We sweep K from 2 to 8 and record the **silhouette** score and **WSSSE**.

**K-selection rule:** within the business-actionable range of 4–6, choose the K whose clusters map to the most
*distinct segment groups* (distinct marketing treatments), and break ties by silhouette.

**Segment naming:** compare each cluster's median R, F and M with the median over all customers:
- recent + frequent + high-spend → Champions. Further clusters in this group become Loyal.
- recent only → Potential
- inactive but historically frequent or valuable → At-Risk
- otherwise → Hibernating / Lost

### 3.5 Customer Value Score and churn risk
**Customer Value Score**
- `CVS = 0.4·M_pct + 0.3·F_pct + 0.3·R_pct`, where each percentile comes from `percent_rank()` and recency is
  inverted.
- Bands: Very High ≥ 80, High ≥ 60, Medium ≥ 40, Low ≥ 20, Very Low < 20.

**Churn risk**, using `OverdueRatio = Recency / max(AvgDaysBetweenOrders, 30)`:

| Risk | Rule |
|---|---|
| High | More than 90 days inactive, and either OverdueRatio > 2 or CVS ≥ 60 |
| Medium | More than 90 days inactive, recency above the median (96 days), or OverdueRatio > 1.5 |
| Low | Everything else |

### 3.6 Market basket analysis
- Each invoice becomes a basket: `collect_set(StockCode)`.
- FP-Growth with minimum confidence 0.2. The minimum support is lowered step by step from 0.02 until 100–500
  rules are found.
- Each rule is reported with its support, confidence and lift.

### 3.7 Recommendation engine
An ordered rule table assigns each customer an action, channel, offer and priority. The first matching rule wins.

| Rule | Condition | Action | Priority |
|---|---|---|---|
| R1 | High churn risk and High/Very High value | Personal win-back outreach + 15% voucher on favourite category | P1 |
| R2 | Champions, Low risk | VIP loyalty: early access, free shipping, referrals | P2 |
| R3 | Champions, cooling | VIP check-in + exclusive bundle | P1 |
| R4 | Loyal | Membership points + cross-sell | P2 |
| R5 / R6 | Potential | Nurture / early re-activation | P3 / P2 |
| R7 | At-Risk | "We miss you" + 10% discount | P2 |
| R8 | Lost, Medium+ value | Seasonal catalogue + 20% comeback offer | P3 |
| R9 | Lost | Newsletter only, excluded from paid campaigns | P4 |

**Product recommendations:**
1. Fire every association rule whose whole antecedent the customer has bought.
2. Drop products the customer already owns.
3. Keep the top 3 by lift.

---

## Chapter 4: Implementation

### 4.1 Pipeline
`python -m src.pipeline` runs 12 stages in about 3 minutes. Each stage is its own module in `src/`. The stages
are: ingestion, cleaning, EDA, features, clustering, profiling, scoring, basket, product behaviour,
recommender, benchmark and charts. Models are saved with MLlib `.write().save()`.

### 4.2 Data cleaning results
The cleaning funnel is in Figure `00_data_quality_funnel.png`.

| Step | Rows remaining | Removed by step |
|---|---:|---:|
| Raw | 1,067,371 | – |
| Customer ID present | 824,364 | 243,007 |
| Not a cancellation | 805,620 | 18,744 |
| Quantity > 0 and Price > 0 | 805,549 | 71 |
| Product codes only (no POST, M, BANK CHARGES, …) | 802,632 | 2,917 |
| Duplicates removed | 776,577 | 26,055 |
| **Reversed orders removed** | **770,417** | **6,160** |

The last step fixes a real data issue. Some purchases were cancelled in full later, such as one customer's single
80,995-unit order of "PAPER CRAFT, LITTLE BIRDIE" (£168K, invoice 581483), cancelled 12 minutes later by
invoice C581484. Dropping only the cancellation
line leaves the original purchase and inflates that customer's value. We match each cancellation to the latest
earlier purchase of the same item and quantity by the same customer, and remove it.

### 4.3 Clean dataset KPIs
| Metric | Value |
|---|---:|
| Customers | 5,839 |
| Orders | 36,333 |
| Products | 4,612 |
| Countries | 41 |
| Revenue | £16.47M |
| Average order value | £453 |

### 4.4 EDA highlights
- The **United Kingdom** accounts for 83.5% of revenue. EIRE, the Netherlands and Germany follow. EIRE has only
  3 customers but £0.57M of revenue (wholesale buyers).
- Revenue is strongly **seasonal**. November is the peak in both years: £1.12M in Nov 2010 and £1.12M in
  Nov 2011. December 2011 looks low only because the data stops on 9 Dec.
- The top products by revenue are the REGENCY CAKESTAND 3 TIER, WHITE HANGING HEART T-LIGHT HOLDER and JUMBO BAG
  RED RETROSPOT.
- The most common order size is £250–500 (12.8K orders). 193 orders exceed £5K.

---

## Chapter 5: Results

### 5.1 Choosing K
The chart is in Figure `01_k_selection.png`.

| K | Silhouette | Segment groups | Segments produced |
|---:|---:|---:|---|
| 2 | **0.514** | 2 | Champions, Lost |
| 3 | 0.380 | 3 | Champions, Loyal, Lost |
| 4 | 0.407 | 3 | Champions, Loyal, Hibernating, Lost |
| **5** | **0.359** | **4** | **Champions, Loyal, At-Risk, Hibernating, Lost** |
| 6 | 0.338 | 4 | Champions, Loyal, Can't Lose Them, At-Risk, Hibernating, Lost |
| 7 | 0.340 | 4 | … two duplicate groups |
| 8 | 0.324 | 5 | … three duplicate groups |

**K = 5 was selected.**
- K = 2 has the highest silhouette, but "best vs rest" isn't actionable.
- K = 4 scores 0.05 higher than K = 5, but merges the At-Risk customers into Hibernating. Those customers need a
  completely different action.
- K = 5 adds a distinct At-Risk segment while keeping a reasonable silhouette (0.36). Values above about 0.25
  indicate meaningful structure.

PCA keeps **73.9%** of the variance in two components (57.97% + 15.96%). The plot is
`03_pca_segments.png`.

### 5.2 Segment profiles
Charts: `02_segment_size_vs_revenue.png`, `05_segment_profile_heatmap.png`.

| Segment | Customers | % of customers | % of revenue | Median recency (d) | Median orders | Median spend | Mean cancellation rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| Champions | 1,026 | 17.6% | **71.8%** | 18 | 14 | £5,617 | 0.19 |
| Loyal | 1,521 | 26.1% | 15.3% | 41 | 5 | £1,403 | 0.07 |
| At-Risk | 883 | 15.1% | 6.4% | 236 | 3 | £854 | **0.41** |
| Hibernating | 1,354 | 23.2% | 5.4% | 318 | 1 | £469 | 0.00 |
| Lost | 1,055 | 18.1% | 1.2% | 337 | 1 | £156 | 0.03 |

### 5.3 Value and churn
- Value bands across all customers: Very High 845, High 1,247, Medium 1,357, Low 1,256, Very Low 1,134.
- Churn risk across all customers: Low 2,780, Medium 674, High 2,385.

The churn risk mix by segment is in `10_churn_risk_by_segment.png`:

| Segment | Low | Medium | High |
|---|---:|---:|---:|
| Champions | 87% | 4% | 9% |
| Loyal | 70% | 7% | 22% |
| At-Risk | 29% | 19% | 52% |
| Hibernating | 24% | 16% | 60% |
| Lost | 22% | 13% | 65% |

### 5.4 Market basket analysis
- **144 rules** at minimum support 0.015, from 36,333 baskets.
- The strongest pairs have lift between 17 and 33:

| If a customer buys | They also buy | Confidence | Lift |
|---|---|---:|---:|
| PINK REGENCY TEACUP AND SAUCER | GREEN REGENCY TEACUP AND SAUCER | 0.84 | 32.5 |
| TOILET METAL SIGN | BATHROOM METAL SIGN | 0.76 | 30.0 |
| GREEN REGENCY TEACUP AND SAUCER | ROSES REGENCY TEACUP AND SAUCER | 0.79 | 27.3 |
| BLUE 3 PIECE MINI DOTS CUTLERY SET | PINK 3 PIECE MINI DOTS CUTLERY SET | 0.70 | 25.8 |
| DOLLY GIRL LUNCH BOX | SPACEBOY LUNCH BOX | 0.67 | 22.1 |

The rules are dominated by **colour and design variants of the same product line**. Customers collect sets, which
is a clear cross-sell lever. **4,567 of 5,839 customers (78%)** receive at least one personalised product
recommendation.

### 5.5 Recommendation output
| Rule | Customers | Historical spend |
|---|---:|---:|
| R2 Champion active (VIP loyalty) | 889 | £10.69M |
| R4 Loyal (membership + cross-sell) | 1,349 | £2.05M |
| **R1 Valuable & slipping (P1 win-back)** | **309** | **£1.42M** |
| R7 At-Risk (win-back discount) | 844 | £0.90M |
| R8 Lost but worth trying | 393 | £0.41M |
| R3 Champion cooling (P1 check-in) | 42 | £0.33M |
| R9 Lost (newsletter only) | 2,013 | £0.66M |

Priority mix: P1 351, P2 3,082, P3 393, P4 2,013. A further 978 customers carry a "high cancellations — review
service" flag.

### 5.6 Pandas vs PySpark benchmark
The chart is `12_benchmark.png`. Both engines run the same RFM aggregation on the same Parquet files, best of
3 runs, on one laptop.

| Scale | Rows | pandas | PySpark |
|---|---:|---:|---:|
| 1× | 0.77M | **0.06 s** | 0.33 s |
| 5× | 3.85M | **0.31 s** | 0.35 s |
| 10× | 7.70M | 0.66 s | **0.65 s** |
| 20× | 15.4M | 1.56 s | **1.31 s** |
| 40× | 30.8M | 6.05 s | **5.67 s** |

- Spark pays fixed JVM and job-scheduling overhead, so pandas wins on small data.
- The two engines are level at about 8M rows, and PySpark is ahead from about 15M rows, even on one machine.
- pandas has to hold all the data in Python memory. Its time jumps 4× from 20× to 40× scale as memory pressure
  builds.
- Spark can spill to disk and, more importantly, run the same code on a cluster by changing only the Spark
  master.

---

## Chapter 6: Business insights and recommendations

1. **Protect the Champions.** 17.6% of customers bring in 71.8% of revenue. They order every 47 days on average,
   buy about 228 different products, and 87% are currently low-risk. Use non-discount VIP perks (early access,
   free shipping, referrals) rather than eroding margin with discounts.
2. **Act now on 309 "valuable & slipping" customers.** £1.42M (8.6%) of historical revenue sits with
   High/Very-High value customers who are already high churn risk. Of these, 172 are Loyal and 95 are Champions.
   They are the P1 list for personal outreach this week.
3. **The At-Risk segment has a service problem, not just a marketing problem.** Its mean cancellation rate is 41%,
   against 7% for Loyal customers. A discount alone won't win them back. Investigate fulfilment, stock-outs and
   returns for these accounts. 978 customers are flagged for service review.
4. **Cross-sell sets.** The strongest associations are matching variants: teacup colours, bathroom and toilet signs,
   lunch-box designs. Bundle "complete the set" offers on product pages and in Loyal and Potential emails.
5. **Plan for November.** Revenue peaks every November at about £1.12M. Time win-back and re-engagement campaigns
   for September–October, so lapsed customers return before the gifting season.
6. **Spend nothing on the Lost tail.** 2,013 customers (34%) have a low-value, long-lapsed history and account for
   only 4% of spend. Keep them on the newsletter and exclude them from paid retargeting.
7. **Kitchen & Dining leads every segment** at 20–25% of revenue. It is the safest default category for offers.

---

## Chapter 7: Conclusion and future scope

### Conclusion
The system turns 1.07M raw transactions into a ranked, explainable action list. Every customer gets:
- a data-driven segment
- a 0–100 value score
- a churn-risk level
- a prioritised action with a channel and offer
- up to 3 cross-sell products

Everything is computed with Spark DataFrames, Spark SQL and MLlib, so the code scales from a laptop to a cluster
unchanged. The work also surfaced a data-quality issue (reversed bulk orders) that would otherwise have distorted
the segments.

### Limitations
- Product categories come from a keyword heuristic. 17.8% of revenue falls into "Other".
- Churn risk uses transparent rules, not a validated predictive model, because there is no churn label.
- The data covers only two years and is mostly UK (83.5% of revenue).
- K-Means assumes compact, roughly spherical clusters. The silhouette of 0.36 shows overlap between neighbouring
  segments.
- The recommendation rules and offers are designed, not A/B tested.

### Future scope
- **Supervised churn model.** Label customers as churned if they made no purchase in the following 90 days, then
  train MLlib gradient-boosted trees on the same features.
- **Structured Streaming.** Ingest invoices live and update scores incrementally.
- **Collaborative filtering** (MLlib ALS) for long-tail recommendations beyond FP-Growth.
- Proper product taxonomy and margin data, to optimise offers by profit rather than revenue.
- A/B testing framework to measure each campaign's uplift.
- Deploy on a managed Spark cluster (Databricks, EMR or Dataproc) by changing the Spark master.

---

## Appendix: How to reproduce
```bash
./scripts/setup_env.sh
python scripts/download_data.py
python -m src.pipeline
pytest -q
streamlit run app/streamlit_app.py
```
