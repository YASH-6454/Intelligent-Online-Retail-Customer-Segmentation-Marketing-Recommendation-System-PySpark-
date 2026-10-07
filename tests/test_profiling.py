import pandas as pd

from src.profiling import base_group, name_clusters


def test_base_group():
    assert base_group(0.3, 3.0, 4.0) == "Champions"
    assert base_group(0.5, 0.5, 0.6) == "Potential"
    assert base_group(3.0, 2.0, 2.5) == "At-Risk"
    assert base_group(4.0, 0.5, 0.4) == "Lost"


def test_name_clusters_handles_duplicates():
    profile = pd.DataFrame({
        "Cluster": [0, 1, 2, 3, 4],
        "Recency_median": [10, 20, 30, 200, 300],
        "Frequency_median": [20, 8, 1, 3, 1],
        "Monetary_median": [5000, 2000, 300, 1500, 150],
    })
    named = name_clusters(profile, {"Recency": 50, "Frequency": 3, "Monetary": 700}).set_index("Cluster")
    assert named.loc[0, "Segment"] == "Champions"
    assert named.loc[1, "Segment"] == "Loyal" and named.loc[1, "SegmentGroup"] == "Loyal"
    assert named.loc[2, "Segment"] == "Potential"
    assert named.loc[3, "Segment"] == "At-Risk"
    assert named.loc[4, "Segment"] == "Lost"
    assert named["Segment"].is_unique
