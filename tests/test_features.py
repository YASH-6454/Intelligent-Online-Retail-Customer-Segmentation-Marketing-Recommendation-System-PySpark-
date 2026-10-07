from datetime import datetime

import pytest
from pyspark.sql import functions as F

from src.features import build_customer_features


def _tx(spark, rows):
    df = spark.createDataFrame(rows, ["CustomerID", "Invoice", "StockCode", "Quantity", "InvoiceDate",
                                      "Revenue", "Country"])
    return df.withColumn("InvoiceMonth", F.date_format("InvoiceDate", "yyyy-MM"))


def test_rfm_and_behaviour(spark):
    tx = _tx(spark, [
        (1, "A1", "X", 2, datetime(2011, 1, 1, 9), 10.0, "United Kingdom"),
        (1, "A1", "Y", 1, datetime(2011, 1, 1, 9), 5.0, "United Kingdom"),
        (1, "A2", "X", 4, datetime(2011, 1, 11, 9), 20.0, "United Kingdom"),
        (1, "A3", "Z", 1, datetime(2011, 2, 10, 9), 15.0, "United Kingdom"),
        (2, "B1", "X", 1, datetime(2011, 2, 20, 9), 50.0, "France"),   # sets max date
    ])
    cancelled = spark.createDataFrame([(1, "C9")], ["CustomerID", "Invoice"])
    f = {r.CustomerID: r for r in build_customer_features(tx, cancelled).collect()}

    c1 = f[1]
    assert c1.Recency == 11              # ref = 2011-02-21, last purchase 2011-02-10
    assert c1.Frequency == 3
    assert c1.Monetary == 50.0
    assert c1.AvgOrderValue == pytest.approx(50 / 3, abs=0.01)
    assert c1.TotalItems == 8
    assert c1.UniqueProducts == 3
    assert c1.ActiveMonths == 2
    assert c1.TenureDays == 40
    assert c1.AvgDaysBetweenOrders == 20.0   # gaps 10 and 30
    assert c1.CancellationRate == 0.25       # 1 cancelled of 4 invoices
    assert c1.IsUK == 1

    c2 = f[2]
    assert c2.Recency == 1 and c2.Frequency == 1
    assert c2.AvgDaysBetweenOrders is None and c2.CancellationRate == 0.0
