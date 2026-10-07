"""Stage 8 - market basket analysis with MLlib FP-Growth (association rules)."""
import pandas as pd
from pyspark.ml.fpm import FPGrowth, FPGrowthModel
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from src import config


def product_names(tx: DataFrame) -> DataFrame:
    return tx.groupBy("StockCode").agg(F.mode("Description").alias("Description"))


def baskets(tx: DataFrame) -> DataFrame:
    return tx.groupBy("Invoice").agg(F.collect_set("StockCode").alias("items"))


def fit_rules(basket_df: DataFrame) -> tuple[FPGrowthModel, DataFrame, float]:
    """Walk down the support ladder until the rule count reaches the target range."""
    lo, hi = config.FP_TARGET_RULES
    model, rules, support = None, None, None
    for support in config.FP_SUPPORT_LADDER:
        model = FPGrowth(itemsCol="items", minSupport=support,
                         minConfidence=config.FP_MIN_CONFIDENCE).fit(basket_df)
        rules = model.associationRules.cache()
        n = rules.count()
        print(f"    minSupport={support}: {n} rules")
        if n >= lo:
            break
    if rules.count() > hi:
        rules = rules.orderBy(F.desc("lift")).limit(hi)
    return model, rules, support


def describe_rules(rules: DataFrame, names: DataFrame) -> pd.DataFrame:
    name_map = dict(names.toPandas().values)
    pdf = rules.toPandas()
    pdf["AntecedentDesc"] = pdf["antecedent"].map(lambda xs: " + ".join(name_map.get(x, x) for x in xs))
    pdf["ConsequentDesc"] = pdf["consequent"].map(lambda xs: " + ".join(name_map.get(x, x) for x in xs))
    pdf["antecedent"] = pdf["antecedent"].map(lambda xs: ",".join(xs))
    pdf["consequent"] = pdf["consequent"].map(lambda xs: ",".join(xs))
    for c in ("confidence", "lift", "support"):
        pdf[c] = pdf[c].round(4)
    return pdf.sort_values(["lift", "confidence"], ascending=False).reset_index(drop=True)


def run(spark: SparkSession, tx: DataFrame) -> tuple[DataFrame, pd.DataFrame, dict]:
    b = baskets(tx).cache()
    model, rules, support = fit_rules(b)
    names = product_names(tx)
    rules_pdf = describe_rules(rules, names)
    rules_pdf.to_csv(config.FINAL_DIR / "association_rules.csv", index=False)
    itemsets = (model.freqItemsets.withColumn("size", F.size("items"))
                .orderBy(F.desc("freq")).limit(50).toPandas())
    itemsets["items"] = itemsets["items"].map(lambda xs: ",".join(xs))
    itemsets.to_csv(config.FINAL_DIR / "frequent_itemsets.csv", index=False)
    model.write().overwrite().save(str(config.MODELS_DIR / "fpgrowth"))
    meta = {"baskets": b.count(), "min_support": support,
            "min_confidence": config.FP_MIN_CONFIDENCE, "rules": len(rules_pdf)}
    return rules, rules_pdf, meta
