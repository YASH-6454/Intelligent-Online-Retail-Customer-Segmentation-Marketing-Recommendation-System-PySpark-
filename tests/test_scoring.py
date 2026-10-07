from src.scoring import add_churn_risk, add_value_score


def test_value_score_and_bands(spark):
    rows = [(i, 100 - i * 10, i, float(i * 100)) for i in range(1, 11)]   # customer 10 is best on all
    df = spark.createDataFrame(rows, ["CustomerID", "Recency", "Frequency", "Monetary"])
    out = {r.CustomerID: r for r in add_value_score(df).collect()}
    assert out[10].CVS == 100.0 and out[10].ValueBand == "Very High"
    assert out[1].CVS == 0.0 and out[1].ValueBand == "Very Low"
    assert out[5].CVS < out[6].CVS


def test_churn_risk(spark):
    rows = [  # CustomerID, Recency, AvgDaysBetweenOrders, CVS
        (1, 10, 15.0, 90.0),     # active
        (2, 200, 20.0, 30.0),    # long overdue vs own rhythm
        (3, 120, 100.0, 75.0),   # inactive & valuable
        (4, 120, 100.0, 20.0),   # inactive, low value, not that overdue
        (5, 150, None, 10.0),    # single order customer, 150/90 > 1.5
    ]
    df = spark.createDataFrame(rows, "CustomerID int, Recency int, AvgDaysBetweenOrders double, CVS double")
    risk = {r.CustomerID: r.ChurnRisk for r in add_churn_risk(df).collect()}
    assert risk == {1: "Low", 2: "High", 3: "High", 4: "Medium", 5: "Medium"}
