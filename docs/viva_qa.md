# Viva preparation: likely questions and answers

**Q1. Why PySpark and not just pandas? The dataset fits in memory.**
Today it does: 1M rows is about 100 MB. Our benchmark (report §5.6) is honest about this:
- At 1× scale pandas is 5× faster (0.06 s against 0.33 s), because Spark pays JVM and job-scheduling overhead.
- The two are level at about 8M rows.
- From about 15M rows PySpark is ahead, even on one laptop (31M rows: 5.7 s against 6.1 s). pandas also needs
  all the data in Python memory.

Retail logs grow every day, and the same Spark code runs on a cluster by changing only the master URL. Spark also
gives us SQL, MLlib (K-Means, FP-Growth, PCA) and Parquet in one engine.

**Q2. Why log-transform before K-Means?**
Monetary and Frequency are heavily right-skewed. A few wholesale customers spend over 100× the median. K-Means
minimises squared Euclidean distance, so without `log1p` those outliers dominate the centroids and the "segments"
just become "the 20 biggest customers vs everyone else". The log compresses the tail, and StandardScaler then puts
every feature on the same scale (mean 0, standard deviation 1).

**Q3. How did you choose K? K=2 has the best silhouette.**
We swept K from 2 to 8 and recorded the silhouette score and WSSSE.
- K=2 (silhouette 0.51) only separates "best" from "rest", which isn't actionable.
- Within the business-useful range of 4 to 6, we pick the K whose clusters map to the most *distinct segment
  groups*, meaning distinct marketing treatments, and break ties by silhouette.
- K=4 (0.41) merges the At-Risk customers into Hibernating. K=5 (0.36) separates them, and they need a
  completely different action: win-back plus a service review, because their cancellation rate is 41%.

The choice and the reason are logged automatically in `outputs/models/k_selection.json`.

**Q4. How are cluster names assigned? Isn't that subjective?**
The names are not hard-coded. For each cluster we compute its median recency, frequency and monetary values and
compare them with the median over all customers. A fixed rule maps the pattern to a name: recent + frequent +
high-spend → Champions, and so on. If the data changes, the names follow the data. `profiling.py` is unit-tested.

**Q5. Why did you build a Customer Value Score when you already have clusters?**
Clusters are groups. The CVS is a *continuous ranking* within and across groups, so a campaign can be sorted by
value. It uses percentile ranks, so it is robust to outliers and easy to explain ("this customer is in the top
10%"). The weights are 0.4 M, 0.3 F and 0.3 R. Money is weighted highest because revenue is the business
objective. The weights live in `config.py`.

**Q6. How do you define churn without a churn label?**
The dataset has no "churned" flag, so churn risk is a transparent rule rather than a trained model. It combines
two things:
1. **Absolute inactivity:** no purchase in more than 90 days, which is one retail quarter.
2. **Relative overdue-ness:** recency divided by the customer's own average gap between orders.

A weekly buyer who has been silent for 60 days is more worrying than a twice-a-year buyer silent for 60 days.
Future work is to label historical churn (no purchase in the following N months) and train a classifier.

**Q7. How does FP-Growth work and why not Apriori?**
FP-Growth compresses all the baskets into a prefix tree (the FP-tree) and mines frequent itemsets from it without
generating candidates. It scans the data twice, whereas Apriori scans repeatedly, once per itemset size. Spark
MLlib ships a distributed FP-Growth. We report:
- **support:** how often the items appear together
- **confidence:** P(B | A)
- **lift:** confidence divided by P(B). Lift above 1 means the items are bought together more than chance.

**Q8. How are product recommendations generated per customer?**
1. Take every rule whose *whole* antecedent the customer has already bought.
2. Drop consequents they already own.
3. Keep the top 3 by lift.

This is a Spark join plus a window function, so it scales to millions of customers.

**Q9. What Spark features did you use specifically?**
- DataFrame API with an explicit `StructType` schema
- Parquet with partitioning (`Year`/`Month`) and caching
- Spark SQL temp views with 9 analytical queries
- Window functions: `lag`, `row_number`, `percent_rank`, and a running `SUM OVER`
- Higher-order functions: `transform`, `array_sort`
- MLlib: Pipeline, VectorAssembler, StandardScaler, KMeans, ClusteringEvaluator, PCA, FPGrowth
- Model persistence: `.write().save()`

**Q10. Did you find any data-quality problems?**
Yes: reversed bulk orders. For example, invoice 581483 was 80,995 units of "PAPER CRAFT, LITTLE BIRDIE"
(£168K), and invoice C581484 cancelled it 12 minutes later. Removing only the cancellation line would leave a
fake £168K customer. We match each cancellation to the latest earlier purchase of the same customer, product and
quantity, and remove both. That removed 6,160 lines.

**Q11. Limitations?**
- Product categories come from a keyword heuristic, because the dataset has no category column.
- Churn uses rules, not a validated model.
- The data covers two years and is mostly UK.
- K-Means assumes roughly spherical clusters.
- The recommendation rules are designed, not A/B tested.
