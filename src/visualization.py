"""Static report charts (PNG). Reads the pipeline's saved outputs, so it can rerun without Spark."""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from src import config  # noqa: E402

# Validated categorical order (light mode) - colour follows the entity, assigned in fixed order.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
STATUS = {"Low": "#0ca30c", "Medium": "#fab219", "High": "#d03b3b"}
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
CONTEXT_GRAY = "#d6d5ce"
DIVERGING = LinearSegmentedColormap.from_list("blue_red", ["#184f95", "#6da7ec", "#f0efec", "#ec8a8a", "#b02a2a"])

# Canonical segment order (best -> worst) drives colour slots and sort order everywhere.
SEGMENT_ORDER = ["Champions", "Loyal", "Loyal (II)", "Potential Loyalists", "Potential", "New / Promising",
                 "Can't Lose Them", "At-Risk", "Hibernating", "Lost"]


def segment_colors(segments) -> dict:
    ordered = sorted(set(segments), key=lambda s: SEGMENT_ORDER.index(s) if s in SEGMENT_ORDER else 99)
    return {s: SERIES[i % len(SERIES)] for i, s in enumerate(ordered)}


def ordered_segments(segments) -> list:
    return list(segment_colors(segments).keys())


def _style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"], "font.size": 10,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID,
        "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "legend.labelcolor": INK2,
    })


def _save(fig, name: str):
    fig.tight_layout()
    fig.savefig(config.CHARTS_DIR / name, dpi=160)
    plt.close(fig)


def _hbar(ax, labels, values, colors, fmt="{:,.0f}"):
    y = np.arange(len(labels))
    ax.barh(y, values, color=colors, height=0.62, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(y, labels)
    if not ax.yaxis_inverted():   # shared y-axes would otherwise flip back
        ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", colors=INK2, length=0)
    xmax = max(values) if len(values) else 1
    for yi, v in zip(y, values):
        ax.text(v + xmax * 0.01, yi, fmt.format(v), va="center", color=INK2, fontsize=9)
    ax.set_xlim(0, xmax * 1.15)


# ------------------------------------------------------------------ charts
def k_selection():
    sweep = pd.read_csv(config.MODELS_DIR / "k_sweep.csv")
    sel = json.loads((config.MODELS_DIR / "k_selection.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, col, title in [(axes[0], "silhouette", "Silhouette score by K (higher is better)"),
                           (axes[1], "wssse", "Within-cluster SSE by K (elbow)")]:
        ax.plot(sweep["k"], sweep[col], color=SERIES[0], linewidth=2, marker="o", markersize=7,
                markeredgecolor=SURFACE, markeredgewidth=2)
        chosen = sweep[sweep["k"] == sel["chosen_k"]]
        ax.scatter(chosen["k"], chosen[col], s=140, color=SERIES[1], zorder=5, edgecolor=SURFACE, linewidth=2)
        ax.annotate(f"chosen k={sel['chosen_k']}", (chosen["k"].iloc[0], chosen[col].iloc[0]),
                    textcoords="offset points", xytext=(8, 10), color=INK, fontsize=9)
        ax.set_title(title)
        ax.set_xlabel("K (number of clusters)")
        ax.set_xticks(sweep["k"])
    _save(fig, "01_k_selection.png")


def segment_size_revenue():
    p = pd.read_csv(config.FINAL_DIR / "segment_profiles.csv")
    order = ordered_segments(p["Segment"])
    p = p.set_index("Segment").loc[order]
    colors = [segment_colors(order)[s] for s in order]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), sharey=True)
    _hbar(axes[0], order, p["CustomerShare"] * 100, colors, "{:.1f}%")
    axes[0].set_title("Share of customers")
    _hbar(axes[1], order, p["RevenueShare"] * 100, colors, "{:.1f}%")
    axes[1].set_title("Share of revenue")
    for ax in axes:
        ax.set_xlabel("%")
    _save(fig, "02_segment_size_vs_revenue.png")


def _small_multiples(df, x, y, fname, title, xlabel, ylabel, logy=False):
    segs = ordered_segments(df["Segment"])
    colors = segment_colors(segs)
    n = len(segs)
    cols = min(3, n)
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 3.6 * rows), sharex=True, sharey=True, squeeze=False)
    sample = df.sample(min(len(df), 6000), random_state=config.SEED)
    for ax, seg in zip(axes.flat, segs):
        ax.scatter(sample[x], sample[y], s=8, color=CONTEXT_GRAY, linewidth=0)
        s = sample[sample["Segment"] == seg]
        ax.scatter(s[x], s[y], s=12, color=colors[seg], edgecolor=SURFACE, linewidth=0.4)
        ax.set_title(f"{seg}  (n={int((df['Segment'] == seg).sum()):,})", fontsize=10)
        if logy:
            ax.set_yscale("log")
    for ax in axes.flat[n:]:
        ax.axis("off")
    for ax in axes[-1]:
        ax.set_xlabel(xlabel)
    for ax in axes[:, 0]:
        ax.set_ylabel(ylabel)
    fig.suptitle(title, x=0.01, ha="left", fontweight="bold", color=INK)
    _save(fig, fname)


def scatter_charts():
    ci = pd.read_parquet(config.FINAL_DIR / "customer_intelligence.parquet")
    _small_multiples(ci, "PC1", "PC2", "03_pca_segments.png",
                     "K-Means segments in PCA space (each panel highlights one segment)", "PC1", "PC2")
    _small_multiples(ci[ci["Monetary"] > 0], "Recency", "Monetary", "04_recency_vs_monetary.png",
                     "Recency vs Monetary by segment", "Recency (days)", "Monetary (£, log)", logy=True)


def segment_heatmap():
    p = pd.read_csv(config.FINAL_DIR / "segment_profiles.csv")
    order = ordered_segments(p["Segment"])
    p = p.set_index("Segment").loc[order]
    cols = [f"{c}_mean" for c in config.FEATURE_COLS]
    vals = p[cols]
    z = (vals - vals.mean()) / vals.std(ddof=0).replace(0, 1)
    fig, ax = plt.subplots(figsize=(13, 0.6 * len(order) + 1.8))
    ax.imshow(z.values, cmap=DIVERGING, vmin=-2, vmax=2, aspect="auto")
    ax.set_xticks(range(len(cols)), config.FEATURE_COLS, rotation=30, ha="right")
    ax.set_yticks(range(len(order)), order)
    ax.grid(False)
    for i in range(len(order)):
        for j in range(len(cols)):
            v = vals.iloc[i, j]
            txt = f"{v:,.0f}" if abs(v) >= 100 else (f"{v:.2f}" if abs(v) < 1 else f"{v:.1f}")
            ax.text(j, i, txt, ha="center", va="center", fontsize=8,
                    color="#ffffff" if abs(z.iloc[i, j]) > 1.3 else INK)
    ax.set_title("Segment profiles: feature means (colour = above / below average across segments)")
    _save(fig, "05_segment_profile_heatmap.png")


def monthly_revenue():
    m = pd.read_csv(config.EDA_DIR / "monthly_revenue.csv")
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(m["InvoiceMonth"], m["revenue"] / 1000, color=SERIES[0], linewidth=2, marker="o", markersize=5)
    ax.set_title("Monthly revenue (£ thousands)")
    ax.set_ylabel("£k")
    ax.tick_params(axis="x", rotation=60)
    peak = m.loc[m["revenue"].idxmax()]
    ax.annotate(f"peak {peak.InvoiceMonth}: £{peak.revenue / 1e6:.2f}M", (peak.InvoiceMonth, peak.revenue / 1000),
                textcoords="offset points", xytext=(-110, 0), color=INK, fontsize=9)
    _save(fig, "06_monthly_revenue.png")


def top_lists():
    c = pd.read_csv(config.EDA_DIR / "by_country.csv").head(10)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    _hbar(ax, c["Country"], c["revenue"] / 1000, SERIES[0], "£{:,.0f}k")
    ax.set_title("Top 10 countries by revenue")
    _save(fig, "07_top_countries.png")

    p = pd.read_csv(config.EDA_DIR / "top_products_revenue.csv").head(12)
    fig, ax = plt.subplots(figsize=(10, 5))
    _hbar(ax, p["Description"].str.slice(0, 38), p["revenue"] / 1000, SERIES[0], "£{:,.0f}k")
    ax.set_title("Top 12 products by revenue")
    _save(fig, "08_top_products.png")


def cvs_distribution():
    ci = pd.read_parquet(config.FINAL_DIR / "customer_intelligence.parquet")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.hist(ci["CVS"], bins=40, color=SERIES[0], edgecolor=SURFACE, linewidth=1)
    for threshold, label in config.VALUE_BANDS[:-1]:
        ax.axvline(threshold, color=MUTED, linewidth=1, linestyle="--")
    for (lo, label), hi in zip(reversed(config.VALUE_BANDS), [20, 40, 60, 80, 100]):
        ax.text((lo + hi) / 2, ax.get_ylim()[1] * 0.95, label, ha="center", color=INK2, fontsize=9)
    ax.set_title("Customer Value Score distribution with value bands")
    ax.set_xlabel("CVS (0-100)")
    ax.set_ylabel("Customers")
    _save(fig, "09_cvs_distribution.png")


def churn_by_segment():
    ci = pd.read_parquet(config.FINAL_DIR / "customer_intelligence.parquet")
    order = ordered_segments(ci["Segment"])
    ct = pd.crosstab(ci["Segment"], ci["ChurnRisk"], normalize="index").reindex(order).fillna(0) * 100
    fig, ax = plt.subplots(figsize=(11, 0.55 * len(order) + 1.6))
    left = np.zeros(len(order))
    for risk in ["Low", "Medium", "High"]:
        vals = ct.get(risk, pd.Series(0, index=order)).values
        ax.barh(order, vals, left=left, color=STATUS[risk], edgecolor=SURFACE, linewidth=2, height=0.6,
                label=f"{risk} risk")
        for i, v in enumerate(vals):
            if v >= 7:
                ax.text(left[i] + v / 2, i, f"{risk[0]} {v:.0f}%", ha="center", va="center", fontsize=8, color=INK)
        left += vals
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)
    ax.set_title("Churn risk mix within each segment (% of customers)")
    _save(fig, "10_churn_risk_by_segment.png")


def top_rules():
    r = pd.read_csv(config.FINAL_DIR / "association_rules.csv")
    pair = r.apply(lambda x: "|".join(sorted([x["antecedent"], x["consequent"]])), axis=1)
    r = r.assign(pair=pair).drop_duplicates("pair").head(15)   # keep the higher-confidence direction
    labels = (r["AntecedentDesc"].str.slice(0, 40) + "  ->  " + r["ConsequentDesc"].str.slice(0, 30))
    fig, ax = plt.subplots(figsize=(12, 6))
    _hbar(ax, labels, r["lift"], SERIES[0], "lift {:.1f}")
    ax.set_title("Top 15 product pairs by lift (FP-Growth; one direction per pair)")
    ax.tick_params(axis="y", labelsize=8)
    _save(fig, "11_top_association_rules.png")


def benchmark():
    path = config.FINAL_DIR / "benchmark.csv"
    if not path.exists():
        return
    b = pd.read_csv(path)
    scales = list(dict.fromkeys(b["scale"]))
    x = np.arange(len(scales))
    fig, ax = plt.subplots(figsize=(8, 4))
    for i, (engine, color) in enumerate([("pandas", SERIES[0]), ("pyspark", SERIES[1])]):
        vals = b[b["engine"] == engine].set_index("scale").loc[scales, "seconds"].values
        ax.bar(x + (i - 0.5) * 0.36, vals, width=0.34, color=color, label=engine, edgecolor=SURFACE, linewidth=2)
        for xi, v in zip(x, vals):
            ax.text(xi + (i - 0.5) * 0.36, v, f"{v:.2f}s" if v < 1 else f"{v:.1f}s", ha="center", va="bottom", fontsize=8, color=INK2)
    rows = b.drop_duplicates("scale").set_index("scale").loc[scales, "rows"]
    ax.set_xticks(x, [f"{s}\n{r / 1e6:.1f}M rows" for s, r in zip(scales, rows)])
    ax.set_ylabel("seconds (best of runs)")
    ax.set_title("RFM aggregation time: pandas vs PySpark (single laptop)")
    ax.grid(axis="x", visible=False)
    ax.legend()
    _save(fig, "12_benchmark.png")


def data_quality():
    dq = pd.read_csv(config.EDA_DIR / "data_quality.csv")
    fig, ax = plt.subplots(figsize=(9, 3.6))
    _hbar(ax, dq["step"], dq["rows"], SERIES[0])
    ax.set_title("Cleaning funnel: rows remaining after each rule")
    _save(fig, "00_data_quality_funnel.png")


def make_all():
    _style()
    for fn in [data_quality, k_selection, segment_size_revenue, scatter_charts, segment_heatmap,
               monthly_revenue, top_lists, cvs_distribution, churn_by_segment, top_rules, benchmark]:
        fn()
    print(f"  charts -> {config.CHARTS_DIR}")


if __name__ == "__main__":
    make_all()
