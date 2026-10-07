"""Stage 5 - MLlib: log1p -> VectorAssembler -> StandardScaler -> K-Means sweep -> final model + PCA."""
import json

import pandas as pd
from pyspark.ml import Pipeline, PipelineModel
from pyspark.ml.clustering import KMeans, KMeansModel
from pyspark.ml.evaluation import ClusteringEvaluator
from pyspark.ml.feature import PCA, StandardScaler, VectorAssembler
from pyspark.ml.functions import vector_to_array
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from src import config
from src.profiling import build_profile


def model_input_cols() -> list[str]:
    return [f"log_{c}" if c in config.LOG_FEATURES else c for c in config.CLUSTER_FEATURES]


def add_log_features(feats: DataFrame) -> DataFrame:
    for c in config.LOG_FEATURES:
        feats = feats.withColumn(f"log_{c}", F.log1p(F.col(c).cast("double")))
    return feats


def build_prep_pipeline() -> Pipeline:
    assembler = VectorAssembler(inputCols=model_input_cols(), outputCol="features")
    scaler = StandardScaler(inputCol="features", outputCol="scaled", withMean=True, withStd=True)
    return Pipeline(stages=[assembler, scaler])


def sweep_k(data: DataFrame, feats: DataFrame, k_values=config.K_RANGE) -> pd.DataFrame:
    """Fit K-Means for each K; record silhouette, WSSSE and how many distinct actionable
    segment groups (= distinct marketing treatments) the clusters map to."""
    evaluator = ClusteringEvaluator(featuresCol="scaled", predictionCol="prediction",
                                    metricName="silhouette", distanceMeasure="squaredEuclidean")
    rows = []
    for k in k_values:
        model = KMeans(k=k, seed=config.SEED, maxIter=config.KMEANS_MAX_ITER,
                       featuresCol="scaled").fit(data)
        preds = model.transform(data)
        profile = build_profile(feats.join(preds.select("CustomerID", F.col("prediction").alias("Cluster")),
                                           "CustomerID"))
        rows.append({"k": k,
                     "silhouette": round(evaluator.evaluate(preds), 4),
                     "wssse": round(model.summary.trainingCost, 2),
                     "min_cluster_size": min(model.summary.clusterSizes),
                     "segment_groups": profile["SegmentGroup"].nunique(),
                     "segments": ", ".join(profile["Segment"])})
        r = rows[-1]
        print(f"    k={k}: silhouette={r['silhouette']:.4f} wssse={r['wssse']:.0f} "
              f"groups={r['segment_groups']} [{r['segments']}]")
    return pd.DataFrame(rows)


def choose_k(sweep: pd.DataFrame) -> dict:
    """Within the business range, maximise distinct actionable segment groups; tie-break on silhouette."""
    lo, hi = config.K_BUSINESS_RANGE
    best_overall = sweep.loc[sweep["silhouette"].idxmax()]
    in_range = sweep[(sweep["k"] >= lo) & (sweep["k"] <= hi)]
    chosen = in_range.sort_values(["segment_groups", "silhouette"], ascending=False).iloc[0]
    best_sil_in_range = in_range.loc[in_range["silhouette"].idxmax()]
    reason = (f"k={int(chosen.k)} gives the most distinct actionable segment groups "
              f"({int(chosen.segment_groups)}: {chosen.segments}) within the business range {lo}-{hi}, "
              f"with silhouette {chosen.silhouette:.3f}.")
    if int(best_sil_in_range.k) != int(chosen.k):
        reason += (f" k={int(best_sil_in_range.k)} has a higher silhouette ({best_sil_in_range.silhouette:.3f}) "
                   f"but only {int(best_sil_in_range.segment_groups)} groups ({best_sil_in_range.segments}).")
    if int(best_overall.k) < lo:
        reason += (f" k={int(best_overall.k)} is the global silhouette maximum ({best_overall.silhouette:.3f}) "
                   f"but splits customers into too few groups to target differently.")
    return {"chosen_k": int(chosen.k), "chosen_silhouette": float(chosen.silhouette),
            "chosen_segment_groups": int(chosen.segment_groups),
            "best_overall_k": int(best_overall.k), "best_overall_silhouette": float(best_overall.silhouette),
            "reason": reason}


def run(feats: DataFrame, k: int | None = None) -> tuple[DataFrame, dict, pd.DataFrame]:
    data = add_log_features(feats)
    prep = build_prep_pipeline().fit(data)
    scaled = prep.transform(data).select("CustomerID", "scaled").cache()

    print("  K-Means sweep:")
    sweep = sweep_k(scaled, feats)
    sweep.to_csv(config.MODELS_DIR / "k_sweep.csv", index=False)
    selection = choose_k(sweep)
    if k is not None:
        sil = float(sweep.loc[sweep["k"] == k, "silhouette"].iloc[0]) if k in set(sweep["k"]) else None
        selection.update(chosen_k=k, chosen_silhouette=sil,
                         reason=f"k={k} fixed by caller (silhouette-best in range was {selection['chosen_k']}).")
    (config.MODELS_DIR / "k_selection.json").write_text(json.dumps(selection, indent=2))

    kmeans = KMeans(k=selection["chosen_k"], seed=config.SEED, maxIter=config.KMEANS_MAX_ITER,
                    featuresCol="scaled", predictionCol="Cluster").fit(scaled)
    pca = PCA(k=2, inputCol="scaled", outputCol="pca").fit(scaled)
    selection["pca_explained_variance"] = [round(float(v), 4) for v in pca.explainedVariance]
    (config.MODELS_DIR / "k_selection.json").write_text(json.dumps(selection, indent=2))

    prep.write().overwrite().save(str(config.MODELS_DIR / "prep_pipeline"))
    kmeans.write().overwrite().save(str(config.MODELS_DIR / "kmeans"))
    pca.write().overwrite().save(str(config.MODELS_DIR / "pca"))

    assigned = (pca.transform(kmeans.transform(scaled))
                   .withColumn("pc", vector_to_array("pca"))
                   .select("CustomerID", "Cluster",
                           F.round(F.col("pc")[0], 4).alias("PC1"),
                           F.round(F.col("pc")[1], 4).alias("PC2")))
    return assigned, selection, sweep


def load_models() -> tuple[PipelineModel, KMeansModel]:
    return (PipelineModel.load(str(config.MODELS_DIR / "prep_pipeline")),
            KMeansModel.load(str(config.MODELS_DIR / "kmeans")))
