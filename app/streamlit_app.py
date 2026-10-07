"""Customer Intelligence dashboard.  Run:  streamlit run app/streamlit_app.py
Reads the pipeline's saved outputs (no Spark at runtime), so it loads instantly."""
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config  # noqa: E402
from src.visualization import INK2, MUTED, SERIES, STATUS, ordered_segments, segment_colors  # noqa: E402

st.set_page_config(page_title="Retail Customer Intelligence", page_icon="🛍️", layout="wide")

PRIORITY_HELP = {"P1": "act this week", "P2": "this month", "P3": "next campaign", "P4": "newsletter only"}


# ------------------------------------------------------------------ data
@st.cache_data
def load():
    f = config.FINAL_DIR
    d = {
        "ci": pd.read_parquet(f / "customer_intelligence.parquet"),
        "profiles": pd.read_csv(f / "segment_profiles.csv"),
        "rules": pd.read_csv(f / "association_rules.csv"),
        "top_products": pd.read_csv(f / "segment_top_products.csv"),
        "category_mix": pd.read_csv(f / "segment_category_mix.csv"),
        "monthly": pd.read_csv(config.EDA_DIR / "monthly_revenue.csv"),
        "countries": pd.read_csv(config.EDA_DIR / "by_country.csv"),
        "dq": pd.read_csv(config.EDA_DIR / "data_quality.csv"),
        "sweep": pd.read_csv(config.MODELS_DIR / "k_sweep.csv"),
        "k_sel": json.loads((config.MODELS_DIR / "k_selection.json").read_text()),
        "kpis": json.loads((config.EDA_DIR / "kpis.json").read_text()),
        "rec_rules": pd.read_csv(f / "recommendation_rules.csv"),
    }
    bench = f / "benchmark.csv"
    d["bench"] = pd.read_csv(bench) if bench.exists() else None
    return d


def style(fig, height=360):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="#fcfcfb",
                      paper_bgcolor="#fcfcfb", font=dict(color=INK2), legend_title_text="",
                      hoverlabel=dict(bgcolor="white"))
    fig.update_xaxes(gridcolor="#e1e0d9", linecolor="#c3c2b7", tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor="#e1e0d9", linecolor="#c3c2b7", tickfont=dict(color=MUTED))
    return fig


def money(v):
    return f"£{v / 1e6:.2f}M" if v >= 1e6 else f"£{v:,.0f}"


if not (config.FINAL_DIR / "customer_intelligence.parquet").exists():
    st.error("No pipeline outputs yet. Run `python -m src.pipeline` first.")
    st.stop()

D = load()
CI = D["ci"]
SEGS = ordered_segments(CI["Segment"])
SEG_COLORS = segment_colors(SEGS)


# ------------------------------------------------------------------ pages
def overview():
    st.title("Online Retail — Customer Intelligence")
    st.caption("Who are our customers, how valuable are they, who is at risk, and what should we do?")
    k = D["kpis"]
    c = st.columns(5)
    c[0].metric("Customers", f"{int(k['customers']):,}", border=True)
    c[1].metric("Revenue", money(k["revenue"]), border=True)
    c[2].metric("Orders", f"{int(k['orders']):,}", border=True)
    c[3].metric("Avg order value", f"£{k['avg_order_value']:,.0f}", border=True)
    at_risk_rev = CI.loc[(CI["ChurnRisk"] == "High") & CI["ValueBand"].isin(["Very High", "High"]), "Monetary"].sum()
    c[4].metric("Revenue at risk (high-value, high-risk)", money(at_risk_rev), border=True)

    left, right = st.columns([3, 2])
    m = D["monthly"]
    fig = px.line(m, x="InvoiceMonth", y="revenue", markers=True, title="Monthly revenue",
                  labels={"revenue": "Revenue (£)", "InvoiceMonth": ""})
    fig.update_traces(line=dict(color=SERIES[0], width=2), marker=dict(size=7))
    left.plotly_chart(style(fig))

    p = D["profiles"].set_index("Segment").loc[SEGS].reset_index()
    long = pd.concat([p.assign(Metric="Customers", Share=p["CustomerShare"] * 100),
                      p.assign(Metric="Revenue", Share=p["RevenueShare"] * 100)])
    fig = px.bar(long, y="Metric", x="Share", color="Segment", orientation="h",
                 color_discrete_map=SEG_COLORS, category_orders={"Segment": SEGS},
                 title="Segment share of customers vs revenue (%)", labels={"Share": "%", "Metric": ""})
    fig.update_traces(marker_line_color="#fcfcfb", marker_line_width=2)
    right.plotly_chart(style(fig))

    st.subheader("Segment summary")
    show = p[["Segment", "Customers", "CustomerShare", "RevenueShare", "Recency_median",
              "Frequency_median", "Monetary_median"]].rename(columns={
        "CustomerShare": "% customers", "RevenueShare": "% revenue", "Recency_median": "Median recency (d)",
        "Frequency_median": "Median orders", "Monetary_median": "Median spend (£)"})
    st.dataframe(show, hide_index=True, column_config={
        "% customers": st.column_config.NumberColumn(format="percent"),
        "% revenue": st.column_config.NumberColumn(format="percent")})


def segments():
    st.title("Segments")
    seg = st.selectbox("Segment", SEGS)
    p = D["profiles"].set_index("Segment").loc[seg]
    c = st.columns(4)
    c[0].metric("Customers", f"{int(p['Customers']):,}", border=True)
    c[1].metric("Revenue share", f"{p['RevenueShare'] * 100:.1f}%", border=True)
    c[2].metric("Median recency", f"{p['Recency_median']:.0f} days", border=True)
    c[3].metric("Median spend", money(p["Monetary_median"]), border=True)

    left, right = st.columns(2)
    sample = CI.sample(min(len(CI), 5000), random_state=1)
    sample["Group"] = sample["Segment"].where(sample["Segment"] == seg, "Other customers")
    fig = px.scatter(sample, x="PC1", y="PC2", color="Group", hover_data=["CustomerID", "Monetary", "Recency"],
                     color_discrete_map={seg: SEG_COLORS[seg], "Other customers": "#d6d5ce"},
                     category_orders={"Group": ["Other customers", seg]}, title=f"{seg} in PCA space")
    fig.update_traces(marker=dict(size=6, line=dict(width=0.5, color="#fcfcfb")))
    left.plotly_chart(style(fig, 400))

    tp = D["top_products"][D["top_products"]["Segment"] == seg]
    fig = px.bar(tp, x="Revenue", y="Description", orientation="h", title=f"Top products bought by {seg}",
                 hover_data=["Quantity", "Buyers"])
    fig.update_traces(marker_color=SERIES[0])
    fig.update_yaxes(autorange="reversed", title="")
    right.plotly_chart(style(fig, 400))

    cm = D["category_mix"][D["category_mix"]["Segment"] == seg].head(8)
    st.markdown("**Category mix (keyword heuristic)** · " +
                " · ".join(f"{r.Category} {r.Share * 100:.0f}%" for r in cm.itertuples()))

    st.subheader("Churn risk and actions in this segment")
    s = CI[CI["Segment"] == seg]
    a, b = st.columns(2)
    risk = (s["ChurnRisk"].value_counts().reindex(["Low", "Medium", "High"]).fillna(0)
            .rename_axis("ChurnRisk").reset_index(name="count"))
    fig = px.bar(risk, x="ChurnRisk", y="count", color="ChurnRisk", color_discrete_map=STATUS,
                 text="count", title="Customers by churn risk")
    a.plotly_chart(style(fig, 300))
    b.dataframe(s.groupby(["Priority", "RecommendedAction"]).size().rename("Customers").reset_index(),
                hide_index=True)


def customer_search():
    st.title("Customer search")
    ids = CI["CustomerID"].astype(int)
    default = int(CI.iloc[0]["CustomerID"])
    cid = st.number_input("Customer ID", min_value=int(ids.min()), max_value=int(ids.max()), value=default, step=1)
    row = CI[CI["CustomerID"] == cid]
    if row.empty:
        st.warning("Customer not found (it may have been removed during cleaning).")
        return
    r = row.iloc[0]
    st.subheader(f"Customer {cid} · {r['Country']}")
    c = st.columns(4)
    c[0].metric("Segment", r["Segment"], border=True)
    c[1].metric("Value", f"{r['ValueBand']} ({r['CVS']:.0f}/100)", border=True)
    c[2].metric("Churn risk", f"{r['ChurnRisk']} ({r['ChurnScore']}/100)", border=True)
    c[3].metric("Priority", f"{r['Priority']} — {PRIORITY_HELP[r['Priority']]}", border=True)

    c = st.columns(6)
    c[0].metric("Recency", f"{r['Recency']} days")
    c[1].metric("Orders", int(r["Frequency"]))
    c[2].metric("Total spend", money(r["Monetary"]))
    c[3].metric("Avg order", f"£{r['AvgOrderValue']:,.0f}")
    c[4].metric("Products", int(r["UniqueProducts"]))
    c[5].metric("Active months", int(r["ActiveMonths"]))

    st.info(f"🎯 **Recommended action:** {r['RecommendedAction']}  \n"
            f"**Channel:** {r['Channel']} · **Offer:** {r['OfferType']} · **Rule:** `{r['RuleId']}`")
    if isinstance(r["RecommendedProducts"], str):
        st.success(f"🛒 **Frequently bought together → recommend:** {r['RecommendedProducts']}")
    st.caption(f"Favourite category: {r['FavouriteCategory']} · First purchase {pd.Timestamp(r['FirstPurchase']).date()}"
               f" · Last purchase {pd.Timestamp(r['LastPurchase']).date()}"
               + (f" · ⚠️ {r['ServiceFlag']}" if isinstance(r["ServiceFlag"], str) else ""))


def market_basket():
    st.title("Market basket analysis (FP-Growth)")
    rules = D["rules"]
    c = st.columns(3)
    min_lift = c[0].slider("Min lift", 1.0, float(rules["lift"].max()), 5.0, 0.5)
    min_conf = c[1].slider("Min confidence", 0.0, 1.0, 0.3, 0.05)
    q = c[2].text_input("Product contains", "")
    f = rules[(rules["lift"] >= min_lift) & (rules["confidence"] >= min_conf)]
    if q:
        mask = f["AntecedentDesc"].str.contains(q, case=False) | f["ConsequentDesc"].str.contains(q, case=False)
        f = f[mask]
    st.caption(f"{len(f)} of {len(rules)} rules")
    st.dataframe(f[["AntecedentDesc", "ConsequentDesc", "support", "confidence", "lift"]]
                 .rename(columns={"AntecedentDesc": "If customer buys", "ConsequentDesc": "They also buy"}),
                 hide_index=True, height=420)
    fig = px.scatter(rules, x="support", y="confidence", size="lift", hover_data=["AntecedentDesc", "ConsequentDesc"],
                     title="All rules: support vs confidence (size = lift)")
    fig.update_traces(marker=dict(color=SERIES[0], line=dict(width=1, color="#fcfcfb")))
    st.plotly_chart(style(fig))


def model_quality():
    st.title("Model & data quality")
    sel = D["k_sel"]
    st.markdown(f"**Chosen K = {sel['chosen_k']}** (silhouette {sel['chosen_silhouette']:.3f}). {sel['reason']}")
    a, b = st.columns(2)
    sw = D["sweep"]
    for col, title, box in [("silhouette", "Silhouette by K", a), ("wssse", "WSSSE by K (elbow)", b)]:
        fig = go.Figure(go.Scatter(x=sw["k"], y=sw[col], mode="lines+markers",
                                   line=dict(color=SERIES[0], width=2), marker=dict(size=8)))
        fig.add_trace(go.Scatter(x=[sel["chosen_k"]], y=sw.loc[sw["k"] == sel["chosen_k"], col],
                                 mode="markers", marker=dict(size=14, color=SERIES[1]), name="chosen"))
        fig.update_layout(title=title, showlegend=False)
        box.plotly_chart(style(fig, 300))

    a, b = st.columns(2)
    dq = D["dq"]
    fig = px.bar(dq, x="rows", y="step", orientation="h", text="rows", title="Cleaning funnel (rows remaining)")
    fig.update_traces(marker_color=SERIES[0], texttemplate="%{text:,}")
    fig.update_yaxes(autorange="reversed", title="")
    a.plotly_chart(style(fig, 320))
    if D["bench"] is not None:
        fig = px.bar(D["bench"], x="scale", y="seconds", color="engine", barmode="group", text="seconds",
                     color_discrete_map={"pandas": SERIES[0], "pyspark": SERIES[1]},
                     hover_data=["rows"], title="RFM aggregation time: pandas vs PySpark")
        b.plotly_chart(style(fig, 320))
    st.subheader("Recommendation rules (first match wins)")
    st.dataframe(D["rec_rules"], hide_index=True)


def action_list():
    st.title("Action list for marketing")
    c = st.columns(3)
    pr = c[0].multiselect("Priority", ["P1", "P2", "P3", "P4"], default=["P1"])
    sg = c[1].multiselect("Segment", SEGS, default=SEGS)
    rk = c[2].multiselect("Churn risk", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
    f = CI[CI["Priority"].isin(pr) & CI["Segment"].isin(sg) & CI["ChurnRisk"].isin(rk)]
    cols = ["CustomerID", "Country", "Segment", "ValueBand", "CVS", "ChurnRisk", "Priority",
            "RecommendedAction", "Channel", "OfferType", "RecommendedProducts", "Recency", "Frequency", "Monetary"]
    st.caption(f"{len(f):,} customers · combined historical spend {money(f['Monetary'].sum())}")
    st.dataframe(f[cols], hide_index=True, height=480)
    st.download_button("Download CSV", f[cols].to_csv(index=False).encode(), "campaign_list.csv", "text/csv")


pg = st.navigation([
    st.Page(overview, title="Overview", icon="📊", default=True),
    st.Page(segments, title="Segments", icon="👥", url_path="segments"),
    st.Page(customer_search, title="Customer search", icon="🔎", url_path="customer"),
    st.Page(market_basket, title="Market basket", icon="🛒", url_path="basket"),
    st.Page(model_quality, title="Model & data quality", icon="🧪", url_path="model"),
    st.Page(action_list, title="Action list", icon="📋", url_path="actions"),
])
pg.run()
