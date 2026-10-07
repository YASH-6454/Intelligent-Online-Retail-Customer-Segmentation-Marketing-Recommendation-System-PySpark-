"""Stage 3 - customer & revenue analytics written as Spark SQL over temp views."""
import json

from pyspark.sql import DataFrame, SparkSession

from src import config

QUERIES = {
    "kpis": """
        SELECT COUNT(*)                                   AS line_items,
               COUNT(DISTINCT Invoice)                    AS orders,
               COUNT(DISTINCT CustomerID)                 AS customers,
               COUNT(DISTINCT StockCode)                  AS products,
               COUNT(DISTINCT Country)                    AS countries,
               ROUND(SUM(Revenue), 2)                     AS revenue,
               ROUND(SUM(Revenue) / COUNT(DISTINCT Invoice), 2) AS avg_order_value,
               MIN(InvoiceDate)                           AS first_date,
               MAX(InvoiceDate)                           AS last_date
        FROM tx""",
    "by_country": """
        SELECT Country,
               COUNT(DISTINCT CustomerID) AS customers,
               COUNT(DISTINCT Invoice)    AS orders,
               ROUND(SUM(Revenue), 2)     AS revenue
        FROM tx GROUP BY Country ORDER BY revenue DESC""",
    "top_products_quantity": """
        SELECT StockCode, FIRST(Description) AS Description,
               SUM(Quantity) AS quantity, ROUND(SUM(Revenue), 2) AS revenue
        FROM tx GROUP BY StockCode ORDER BY quantity DESC LIMIT 20""",
    "top_products_revenue": """
        SELECT StockCode, FIRST(Description) AS Description,
               SUM(Quantity) AS quantity, ROUND(SUM(Revenue), 2) AS revenue
        FROM tx GROUP BY StockCode ORDER BY revenue DESC LIMIT 20""",
    # window function: running total over months
    "monthly_revenue": """
        SELECT InvoiceMonth, revenue, orders, customers,
               ROUND(SUM(revenue) OVER (ORDER BY InvoiceMonth
                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cumulative_revenue
        FROM (SELECT InvoiceMonth, ROUND(SUM(Revenue), 2) AS revenue,
                     COUNT(DISTINCT Invoice) AS orders, COUNT(DISTINCT CustomerID) AS customers
              FROM tx GROUP BY InvoiceMonth)
        ORDER BY InvoiceMonth""",
    "top_customers": """
        SELECT CustomerID, FIRST(Country) AS Country, COUNT(DISTINCT Invoice) AS orders,
               ROUND(SUM(Revenue), 2) AS revenue
        FROM tx GROUP BY CustomerID ORDER BY revenue DESC LIMIT 20""",
    "order_value_distribution": """
        SELECT CASE WHEN v < 100 THEN '1: <100'
                    WHEN v < 250 THEN '2: 100-250'
                    WHEN v < 500 THEN '3: 250-500'
                    WHEN v < 1000 THEN '4: 500-1k'
                    WHEN v < 5000 THEN '5: 1k-5k'
                    ELSE '6: 5k+' END AS order_value_band,
               COUNT(*) AS orders
        FROM (SELECT Invoice, SUM(Revenue) AS v FROM tx GROUP BY Invoice)
        GROUP BY 1 ORDER BY 1""",
    "weekday_hour": """
        SELECT date_format(InvoiceDate, 'E') AS weekday, HOUR(InvoiceDate) AS hour,
               COUNT(DISTINCT Invoice) AS orders
        FROM tx GROUP BY 1, 2""",
    # window function: rank each customer's products by spend
    "customer_top_product": """
        SELECT CustomerID, StockCode, Description, spend
        FROM (SELECT CustomerID, StockCode, FIRST(Description) AS Description,
                     ROUND(SUM(Revenue), 2) AS spend,
                     ROW_NUMBER() OVER (PARTITION BY CustomerID ORDER BY SUM(Revenue) DESC) AS rk
              FROM tx GROUP BY CustomerID, StockCode)
        WHERE rk = 1""",
}


def run(spark: SparkSession, tx: DataFrame) -> dict:
    tx.createOrReplaceTempView("tx")
    results = {}
    for name, sql in QUERIES.items():
        pdf = spark.sql(sql).toPandas()
        pdf.to_csv(config.EDA_DIR / f"{name}.csv", index=False)
        results[name] = pdf
    kpis = json.loads(results["kpis"].to_json(orient="records", date_format="iso"))[0]
    (config.EDA_DIR / "kpis.json").write_text(json.dumps(kpis, indent=2))
    return results
