"""Stage 6 - turn numeric clusters into named business segments using their actual profiles."""
import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from src import config

# Names used when several clusters share a base group, ordered from higher to lower value.
GROUP_NAMES = {
    "Champions": ["Champions", "Loyal", "Loyal (II)"],
    "Potential": ["Potential Loyalists", "New / Promising", "Potential (III)"],
    "At-Risk": ["Can't Lose Them", "At-Risk", "At-Risk (III)"],
    "Lost": ["Hibernating", "Lost", "Lost (III)"],
}
SINGLE_NAMES = {"Champions": "Champions", "Potential": "Potential", "At-Risk": "At-Risk", "Lost": "Lost"}


def base_group(rel_r: float, rel_f: float, rel_m: float) -> str:
    """rel_* = cluster median / overall customer median. Lower recency is better."""
    recent = rel_r <= 1.0
    if recent and rel_f >= 1.0 and rel_m >= 1.0:
        return "Champions"
    if recent:
        return "Potential"
    if rel_f >= 1.0 or rel_m >= 1.0:
        return "At-Risk"
    return "Lost"


def name_clusters(profile: pd.DataFrame, medians: dict) -> pd.DataFrame:
    p = profile.copy()
    p["relR"] = p["Recency_median"] / medians["Recency"]
    p["relF"] = p["Frequency_median"] / medians["Frequency"]
    p["relM"] = p["Monetary_median"] / medians["Monetary"]
    p["BaseGroup"] = [base_group(r, f, m) for r, f, m in zip(p.relR, p.relF, p.relM)]

    names, groups = {}, {}
    for group, members in p.sort_values("Monetary_median", ascending=False).groupby("BaseGroup", sort=False):
        ids = list(members["Cluster"])
        options = [SINGLE_NAMES[group]] if len(ids) == 1 else GROUP_NAMES[group]
        for i, cid in enumerate(ids):
            names[cid] = options[i] if i < len(options) else f"{group} #{i + 1}"
            # within the Champions group only the top cluster is "Champions"; the rest behave as Loyal
            groups[cid] = "Loyal" if group == "Champions" and i > 0 else group
    p["Segment"] = p["Cluster"].map(names)
    p["SegmentGroup"] = p["Cluster"].map(groups)
    return p


def build_profile(df: DataFrame) -> pd.DataFrame:
    """df: customer features + Cluster column -> named per-cluster profile (pandas)."""
    medians = dict(zip(["Recency", "Frequency", "Monetary"],
                       df.approxQuantile(["Recency", "Frequency", "Monetary"], [0.5], 0.001)))
    medians = {k: max(v[0], 1e-9) for k, v in medians.items()}

    total_rev = df.agg(F.sum("Monetary")).first()[0]
    aggs = [F.count("*").alias("Customers"), F.sum("Monetary").alias("Revenue")]
    for c in config.FEATURE_COLS:
        aggs.append(F.round(F.avg(c), 2).alias(f"{c}_mean"))
    for c in ["Recency", "Frequency", "Monetary"]:
        aggs.append(F.percentile_approx(c, 0.5).alias(f"{c}_median"))
    profile = df.groupBy("Cluster").agg(*aggs).toPandas()
    profile["CustomerShare"] = (profile["Customers"] / profile["Customers"].sum()).round(4)
    profile["RevenueShare"] = (profile["Revenue"] / total_rev).round(4)
    return name_clusters(profile, medians).sort_values("Monetary_median", ascending=False)


def run(spark: SparkSession, feats: DataFrame, assigned: DataFrame) -> tuple[DataFrame, pd.DataFrame]:
    df = feats.join(assigned, "CustomerID")
    profile = build_profile(df)
    profile.to_csv(config.FINAL_DIR / "segment_profiles.csv", index=False)
    mapping = spark.createDataFrame(profile[["Cluster", "Segment", "SegmentGroup"]])
    return df.join(mapping, "Cluster"), profile
