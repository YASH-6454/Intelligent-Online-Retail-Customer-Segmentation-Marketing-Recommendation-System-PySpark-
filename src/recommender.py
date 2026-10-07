"""Stage 10 - rule-based marketing engine + association-rule product recommendations."""
from dataclasses import dataclass
from typing import Callable

import pandas as pd
from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

from src import config

HIGH_VALUE = ["Very High", "High"]
MID_PLUS_VALUE = ["Very High", "High", "Medium"]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    when: Callable[[], Column]
    action: str
    channel: str
    offer: str
    priority: str


# Ordered: the first matching rule wins.
RULES = [
    Rule("R1-VALUABLE-SLIPPING",
         lambda: (F.col("ChurnRisk") == "High") & F.col("ValueBand").isin(HIGH_VALUE),
         "Personal win-back: account-manager outreach + voucher on favourite category",
         "Email + Phone", "15% win-back voucher", "P1"),
    Rule("R2-CHAMPION-ACTIVE",
         lambda: (F.col("SegmentGroup") == "Champions") & (F.col("ChurnRisk") == "Low"),
         "VIP loyalty: early access to new ranges, free shipping, referral rewards",
         "Email + Loyalty programme", "VIP perks (no discount)", "P2"),
    Rule("R3-CHAMPION-COOLING",
         lambda: F.col("SegmentGroup") == "Champions",
         "VIP check-in: personalised thank-you + exclusive bundle before they drift",
         "Email", "Exclusive bundle", "P1"),
    Rule("R4-LOYAL",
         lambda: F.col("SegmentGroup") == "Loyal",
         "Membership / points programme + cross-sell from frequently-bought-together items",
         "Email + On-site recommendations", "Double loyalty points", "P2"),
    Rule("R5-POTENTIAL-ACTIVE",
         lambda: (F.col("SegmentGroup") == "Potential") & (F.col("ChurnRisk") == "Low"),
         "Nurture: cross-sell recommended products + second-order incentive",
         "Email + On-site recommendations", "10% off next order", "P3"),
    Rule("R6-POTENTIAL-SLIPPING",
         lambda: F.col("SegmentGroup") == "Potential",
         "Early re-activation: reminder of favourite category + free shipping",
         "Email + Retargeting ads", "Free shipping", "P2"),
    Rule("R7-AT-RISK",
         lambda: F.col("SegmentGroup") == "At-Risk",
         "Win-back campaign: 'We miss you' message with discount",
         "Email + Retargeting ads", "10% discount", "P2"),
    Rule("R8-LOST-WORTH-TRYING",
         lambda: (F.col("SegmentGroup") == "Lost") & F.col("ValueBand").isin(MID_PLUS_VALUE),
         "Re-engagement: seasonal catalogue + comeback offer",
         "Email", "20% comeback offer", "P3"),
    Rule("R9-LOST",
         lambda: F.col("SegmentGroup") == "Lost",
         "Low-cost re-engagement: newsletter only, exclude from paid campaigns",
         "Newsletter", "None", "P4"),
]
DEFAULT = Rule("R0-DEFAULT", lambda: F.lit(True), "Standard newsletter", "Newsletter", "None", "P4")


def _chain(field: str) -> Column:
    expr = None
    for rule in RULES:
        value = F.lit(getattr(rule, field))
        expr = F.when(rule.when(), value) if expr is None else expr.when(rule.when(), value)
    return expr.otherwise(F.lit(getattr(DEFAULT, field)))


def apply_rules(df: DataFrame) -> DataFrame:
    df = df.withColumn("RuleId", _chain("rule_id"))
    for field, col in [("action", "RecommendedAction"), ("channel", "Channel"),
                       ("offer", "OfferType"), ("priority", "Priority")]:
        df = df.withColumn(col, _chain(field))
    return df.withColumn("ServiceFlag",
                         F.when(F.col("CancellationRate") > 0.3, "High cancellations - review service issues"))


def product_recommendations(tx: DataFrame, rules: DataFrame, names: DataFrame,
                            top_n: int = config.TOP_N_PRODUCT_RECS) -> DataFrame:
    """For each customer, fire every rule whose whole antecedent they have bought; recommend unseen consequents."""
    bought = tx.select("CustomerID", F.col("StockCode").alias("item")).distinct()
    r = (rules.withColumn("rule_id", F.monotonically_increasing_id())
              .withColumn("n_ante", F.size("antecedent"))
              .withColumn("rec", F.col("consequent")[0]))
    exploded = r.select("rule_id", "n_ante", "rec", "lift", "confidence",
                        F.explode("antecedent").alias("item"))
    fired = (exploded.join(bought, "item")
                     .groupBy("CustomerID", "rule_id", "n_ante", "rec", "lift", "confidence")
                     .agg(F.count("*").alias("matched"))
                     .filter(F.col("matched") == F.col("n_ante")))
    fresh = fired.join(bought.withColumnRenamed("item", "rec"), ["CustomerID", "rec"], "left_anti")
    best = fresh.groupBy("CustomerID", "rec").agg(F.max("lift").alias("lift"),
                                                  F.max("confidence").alias("confidence"))
    w = Window.partitionBy("CustomerID").orderBy(F.desc("lift"), F.desc("confidence"))
    top = (best.withColumn("rk", F.row_number().over(w)).filter(F.col("rk") <= top_n)
               .join(names.withColumnRenamed("StockCode", "rec"), "rec"))
    return (top.groupBy("CustomerID")
               .agg(F.array_join(F.transform(F.array_sort(F.collect_list(F.struct("rk", "Description"))),
                                             lambda s: s["Description"]), " | ")
                    .alias("RecommendedProducts")))


def rules_table() -> pd.DataFrame:
    return pd.DataFrame([{"RuleId": r.rule_id, "Action": r.action, "Channel": r.channel,
                          "Offer": r.offer, "Priority": r.priority} for r in RULES + [DEFAULT]])


def run(scored: DataFrame, tx: DataFrame, rules: DataFrame, names: DataFrame,
        favourite: DataFrame) -> DataFrame:
    out = (apply_rules(scored)
           .join(product_recommendations(tx, rules, names), "CustomerID", "left")
           .join(favourite, "CustomerID", "left"))
    rules_table().to_csv(config.FINAL_DIR / "recommendation_rules.csv", index=False)
    return out
