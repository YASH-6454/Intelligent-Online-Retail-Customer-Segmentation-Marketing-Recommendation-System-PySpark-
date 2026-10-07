from pyspark.sql import functions as F

from src.product_behaviour import category_expr
from src.recommender import apply_rules, product_recommendations


def test_rule_engine_first_match_wins(spark):
    rows = [  # CustomerID, SegmentGroup, ValueBand, ChurnRisk, CancellationRate
        (1, "Champions", "Very High", "Low", 0.0),
        (2, "Champions", "Very High", "High", 0.0),   # valuable & slipping beats champion rule
        (3, "At-Risk", "Medium", "High", 0.5),
        (4, "Lost", "Very Low", "High", 0.0),
        (5, "Potential", "Medium", "Low", 0.0),
    ]
    df = spark.createDataFrame(rows, ["CustomerID", "SegmentGroup", "ValueBand", "ChurnRisk", "CancellationRate"])
    out = {r.CustomerID: r for r in apply_rules(df).collect()}
    assert out[1].RuleId == "R2-CHAMPION-ACTIVE" and out[1].Priority == "P2"
    assert out[2].RuleId == "R1-VALUABLE-SLIPPING" and out[2].Priority == "P1"
    assert out[3].RuleId == "R7-AT-RISK" and out[3].ServiceFlag is not None
    assert out[4].RuleId == "R9-LOST" and out[4].Priority == "P4"
    assert out[5].RuleId == "R5-POTENTIAL-ACTIVE"


def test_product_recommendations_skip_owned_items(spark):
    tx = spark.createDataFrame([(1, "A"), (1, "B"), (2, "A"), (2, "C")], ["CustomerID", "StockCode"])
    rules = spark.createDataFrame(
        [(["A"], ["C"], 0.5, 3.0), (["A", "B"], ["D"], 0.6, 5.0), (["B"], ["E"], 0.4, 2.0)],
        "antecedent array<string>, consequent array<string>, confidence double, lift double")
    names = spark.createDataFrame([(c, f"Item {c}") for c in "ABCDE"], ["StockCode", "Description"])
    recs = {r.CustomerID: r.RecommendedProducts for r in product_recommendations(tx, rules, names).collect()}
    assert recs[1] == "Item D | Item C | Item E"   # ordered by lift
    assert 2 not in recs                            # owns C already; D/E rules don't fire


def test_category_heuristic(spark):
    df = spark.createDataFrame([("WHITE HANGING HEART T-LIGHT HOLDER",), ("JUMBO BAG RED RETROSPOT",),
                                ("REGENCY CAKESTAND 3 TIER",), ("PAPER CHAIN KIT 50'S CHRISTMAS",),
                                ("ASSORTED COLOUR BIRD ORNAMENT",), ("RANDOM THING",)], ["Description"])
    cats = [r.c for r in df.select(category_expr(F.col("Description")).alias("c")).collect()]
    assert cats == ["Lighting & Candles", "Bags & Storage", "Kitchen & Dining", "Christmas & Seasonal",
                    "Garden & Outdoor", "Other"]
