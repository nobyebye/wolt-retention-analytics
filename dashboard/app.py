"""Read-only analytical dashboard. Start after a successful pipeline run."""

import json
import pandas as pd
import plotly.express as px
import streamlit as st
from wolt_analytics.db import connect, rows

st.set_page_config(page_title="Wolt Retention Lab", page_icon="📊", layout="wide")
st.title("Wolt Retention Lab")
st.caption(
    "Independent portfolio project · MySQL 8 · Official synthetic assignment data · Not affiliated with Wolt"
)


@st.cache_data(ttl=60)
def load():
    with connect() as db:
        runs = rows(
            db,
            "SELECT summary FROM pipeline_runs WHERE status='success' ORDER BY completed_at DESC LIMIT 1",
        )
        if not runs:
            raise ValueError("Run the pipeline first")
        return (
            json.loads(runs[0]["summary"]),
            pd.DataFrame(
                rows(
                    db,
                    "SELECT * FROM mart_retention ORDER BY cohort_month,month_number",
                )
            ),
            pd.DataFrame(rows(db, "SELECT * FROM mart_repurchase")),
            pd.DataFrame(
                rows(db, "SELECT * FROM mart_monthly ORDER BY activity_month")
            ),
        )


try:
    summary, retention, repurchase, monthly = load()
except Exception:
    st.info(
        "No analytics snapshot available. Check the MySQL connection and run the pipeline command in README.md."
    )
    st.stop()

if st.sidebar.button("Refresh snapshot"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.header("Analysis controls")
line = st.sidebar.selectbox("Acquisition product line", ["Restaurant", "Retail store"])
metric = st.sidebar.radio(
    "Retention definition", ["Same product line", "Any platform purchase"]
)
st.sidebar.caption(
    f"Declared observation: {summary['observation_start']} → {summary['as_of']}"
)
st.sidebar.caption(
    "A cohort is a group of customers with the same first-purchase month and product line."
)
a, b, c, d = st.columns(4)
a.metric("Cohort customers", f"{summary['cohort_users']:,}")
b.metric("Reconciled purchase events", f"{summary['clean_events']:,}")
c.metric("Quarantined events", f"{summary['quarantined_events']:,}")
d.metric("Quality checks passed", len(summary["quality_checks"]))
st.warning(
    "Synthetic data: findings describe this dataset only. First-purchase records are included as acquisition anchors; unmatched users are excluded. No revenue or causal uplift claims."
)

tab1, tab2, tab3 = st.tabs(
    ["Cohort retention", "30-day repeat purchase", "Data quality & volume"]
)
with tab1:
    st.subheader(f"{line} · Monthly cohort retention")
    field = (
        "same_line_retention" if metric == "Same product line" else "platform_retention"
    )
    subset = retention[retention.acquisition_line == line].copy()
    subset[field] = pd.to_numeric(subset[field], errors="coerce")
    subset["cohort_month"] = subset.cohort_month.astype(str).str[:7]
    heat = subset.pivot(index="cohort_month", columns="month_number", values=field)
    fig = px.imshow(
        heat,
        text_auto=".0%",
        color_continuous_scale="Blues",
        zmin=0,
        zmax=1,
        labels={
            "x": "Months since first purchase",
            "y": "Acquisition cohort",
            "color": "Retention",
        },
        aspect="auto",
    )
    fig.update_layout(height=420, coloraxis_colorbar_tickformat=".0%")
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Blank = unobserved or incomplete calendar month, never zero. Zero = a fully observed month with no returning users. Cohort size includes all known first-purchase users, including those who never return. September acquisition coverage ends on September 21."
    )
    st.dataframe(
        subset[
            [
                "cohort_month",
                "month_number",
                "cohort_users",
                "eligible",
                "platform_active_users",
                "same_line_active_users",
                field,
            ]
        ],
        hide_index=True,
    )
    st.download_button(
        "Download selected cohort data",
        subset.to_csv(index=False),
        "retention.csv",
        "text/csv",
    )
with tab2:
    st.subheader("Repeat and cross-line purchases within 30 days")
    shown = repurchase.copy()
    for column in ("repeat_rate_30d", "cross_line_rate_30d"):
        shown[column] = pd.to_numeric(shown[column])
    tidy = shown.melt(
        id_vars="acquisition_line",
        value_vars=["repeat_rate_30d", "cross_line_rate_30d"],
        var_name="Metric",
        value_name="Rate",
    )
    fig = px.bar(
        tidy,
        x="acquisition_line",
        y="Rate",
        color="Metric",
        barmode="group",
        color_discrete_sequence=["#009de0", "#163b65"],
    )
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(shown, hide_index=True)
    st.caption(
        "Eligible: first purchase on/after the observation start and at least 30 days before the as-of date. Repeat: another distinct purchase ID in day 0–30, inclusive. Date-only source cannot establish the order of purchases on the same day."
    )
with tab3:
    st.subheader("Observed monthly purchase events")
    monthly["activity_month"] = monthly.activity_month.astype(str)
    st.plotly_chart(
        px.line(
            monthly,
            x="activity_month",
            y="purchase_events",
            color="product_line",
            markers=True,
            color_discrete_sequence=["#009de0", "#163b65"],
        ),
        width="stretch",
    )
    st.caption(
        "Volume includes first-purchase anchors. Partial calendar months are omitted. This is an event-count view, not company revenue."
    )
    st.json(summary)
