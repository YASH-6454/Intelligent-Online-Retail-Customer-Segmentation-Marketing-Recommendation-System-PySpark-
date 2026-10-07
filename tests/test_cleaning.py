from datetime import datetime

from src.cleaning import clean

COLS = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Country", "CustomerID"]
T = datetime(2011, 1, 10, 10, 0)


def test_cleaning_rules(spark):
    rows = [
        ("1001", "85123A", "HEART HOLDER", 6, T, 2.55, "United Kingdom", 1),   # keep
        ("1001", "85123A", "HEART HOLDER", 6, T, 2.55, "United Kingdom", 1),   # duplicate
        ("1002", "22423", "CAKESTAND", 2, T, 12.75, "France", None),           # no customer
        ("C1003", "22423", "CAKESTAND", -1, T, 12.75, "France", 2),            # cancellation
        ("1004", "22423", "CAKESTAND", 0, T, 12.75, "France", 2),              # zero qty
        ("1005", "22423", "CAKESTAND", 1, T, 0.0, "France", 2),                # zero price
        ("1006", "POST", "POSTAGE", 1, T, 18.0, "France", 2),                  # non-product
        ("1007", "test001", "TEST", 1, T, 1.0, "France", 2),                   # test code
        ("1008", "22423", "CAKESTAND", 2, T, 12.75, "France", 2),              # keep
    ]
    df = spark.createDataFrame(rows, COLS)
    clean_df, cancelled, dq = clean(df)

    assert clean_df.count() == 2
    assert {r.Invoice for r in clean_df.collect()} == {"1001", "1008"}
    assert cancelled.count() == 1
    assert clean_df.filter("CustomerID IS NULL").count() == 0
    revenue = {r.Invoice: r.Revenue for r in clean_df.collect()}
    assert revenue["1008"] == 25.5
    assert [d["step"] for d in dq][0] == "raw" and dq[0]["rows"] == 9
    assert dq[-1]["rows"] == 2 and dq[-1]["step"] == "reversed_orders_removed"


def test_reversed_purchase_removed(spark):
    t1, t2, t3 = datetime(2011, 1, 1), datetime(2011, 1, 2), datetime(2011, 1, 3)
    rows = [
        ("2001", "23843", "PAPER CRAFT", 80995, t1, 2.08, "United Kingdom", 9),
        ("C2002", "23843", "PAPER CRAFT", -80995, t2, 2.08, "United Kingdom", 9),   # reverses 2001
        ("2003", "22423", "CAKESTAND", 4, t1, 12.75, "United Kingdom", 9),
        ("2004", "22423", "CAKESTAND", 4, t2, 12.75, "United Kingdom", 9),
        ("C2005", "22423", "CAKESTAND", -4, t3, 12.75, "United Kingdom", 9),        # reverses only 2004
        ("2006", "22423", "CAKESTAND", 2, t1, 12.75, "United Kingdom", 9),          # different qty: kept
    ]
    clean_df, _, dq = clean(spark.createDataFrame(rows, COLS))
    assert sorted(r.Invoice for r in clean_df.collect()) == ["2003", "2006"]
    assert dq[-1]["step"] == "reversed_orders_removed"
