"""Stage 7 - Customer Value Score (0-100) and churn-risk classification."""
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from src import config


def value_band(cvs_col):
    expr = None
    for threshold, label in config.VALUE_BANDS:
        cond = cvs_col >= threshold
        expr = F.when(cond, label) if expr is None else expr.when(cond, label)
    return expr


def add_value_score(df: DataFrame) -> DataFrame:
    # Percentile ranks over all customers (single global window: fine for thousands of customers)
    w_r = Window.orderBy(F.col("Recency").desc())     # most recent customer ranks highest
    w_f = Window.orderBy("Frequency")
    w_m = Window.orderBy("Monetary")
    wt = config.CVS_WEIGHTS
    return (df.withColumn("R_Score", F.round(F.percent_rank().over(w_r) * 100, 1))
              .withColumn("F_Score", F.round(F.percent_rank().over(w_f) * 100, 1))
              .withColumn("M_Score", F.round(F.percent_rank().over(w_m) * 100, 1))
              .withColumn("CVS", F.round(wt["M"] * F.col("M_Score") + wt["F"] * F.col("F_Score")
                                         + wt["R"] * F.col("R_Score"), 1))
              .withColumn("ValueBand", value_band(F.col("CVS"))))


def add_churn_risk(df: DataFrame) -> DataFrame:
    recency_p50 = df.approxQuantile("Recency", [0.5], 0.001)[0]
    # A customer's own buying rhythm; single-order customers are judged against the inactivity window
    gap = F.greatest(F.coalesce(F.col("AvgDaysBetweenOrders"), F.lit(float(config.CHURN_INACTIVE_DAYS))),
                     F.lit(float(config.CHURN_MIN_GAP_DAYS)))
    df = df.withColumn("OverdueRatio", F.round(F.col("Recency") / gap, 2))
    inactive = F.col("Recency") > config.CHURN_INACTIVE_DAYS
    high = inactive & ((F.col("OverdueRatio") > config.CHURN_OVERDUE_HIGH)
                       | (F.col("CVS") >= config.CHURN_HIGH_VALUE_CVS))
    medium = (inactive | (F.col("Recency") > recency_p50)
              | (F.col("OverdueRatio") > config.CHURN_OVERDUE_MEDIUM))
    return (df.withColumn("ChurnRisk", F.when(high, "High").when(medium, "Medium").otherwise("Low"))
              .withColumn("ChurnScore",
                          F.round(F.least(F.col("OverdueRatio") / (2 * config.CHURN_OVERDUE_HIGH), F.lit(1.0)) * 100, 0)
                          .cast("int")))


def run(df: DataFrame) -> DataFrame:
    return add_churn_risk(add_value_score(df))
