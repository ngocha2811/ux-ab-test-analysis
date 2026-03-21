import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from statsmodels.stats.proportion import proportions_ztest, proportion_confint
from scipy import stats
import json
import os

# ─────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="A/B Test Dashboard — UX Completion Rate",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

COLORS = {"Test": "#2563EB", "Control": "#94A3B8"}
BUSINESS_THRESHOLD = 0.05
STEP_ORDER = ["start", "step_1", "step_2", "step_3", "confirm"]

# ─────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────
@st.cache_data
def load_data():
    df = pd.read_csv("output/df_analysis_client_level.csv")
    df_web = pd.read_csv("output/df_web_clean.csv")
    return df, df_web

@st.cache_data
def load_results():
    with open("output/results_summary.json") as f:
        return json.load(f)

try:
    df, df_web = load_data()
    results = load_results()
    data_loaded = True
except FileNotFoundError:
    data_loaded = False

# ─────────────────────────────────────────────
# Sidebar filters
# ─────────────────────────────────────────────
st.sidebar.title("🔬 Filters")
st.sidebar.markdown("Filter results by client segment. Results update live.")

if data_loaded:
    # Age group filter
    df["age_group"] = pd.cut(
        df["clnt_age"].fillna(df["clnt_age"].median()),
        bins=[0, 30, 45, 60, 120],
        labels=["Under 30", "30–44", "45–59", "60+"]
    )
    age_options = ["All"] + list(df["age_group"].cat.categories)
    selected_age = st.sidebar.selectbox("Age Group", age_options)

    # Gender filter, exclude "X" (unknown) category
    gender_options = ["All"] + sorted(df["gendr"].dropna().unique().tolist())[:-1]
    selected_gender = st.sidebar.selectbox("Gender", gender_options)

    # Apply filters
    df_filtered = df.copy()
    if selected_age != "All":
        df_filtered = df_filtered[df_filtered["age_group"] == selected_age]
    if selected_gender != "All":
        df_filtered = df_filtered[df_filtered["gendr"] == selected_gender]

    st.sidebar.markdown("---")
    st.sidebar.metric("Clients in view", f"{len(df_filtered):,}")

# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────
st.title("🧪 A/B Test Dashboard")
st.markdown("**Experiment:** New UX Design — Impact on Process Completion Rate")
st.markdown("---")

if not data_loaded:
    st.error("⚠️ Data not found. Run the analysis notebooks first to generate `output/` files.")
    st.stop()

# ─────────────────────────────────────────────
# Helper: compute stats for filtered data
# ─────────────────────────────────────────────
def compute_stats(df_in):
    test = df_in[df_in["Variation"] == "Test"]
    ctrl = df_in[df_in["Variation"] == "Control"]
    if len(test) < 10 or len(ctrl) < 10:
        return None

    n_test, n_ctrl = len(test), len(ctrl)
    x_test, x_ctrl = test["completed"].sum(), ctrl["completed"].sum()
    rate_test = x_test / n_test
    rate_ctrl = x_ctrl / n_ctrl
    abs_lift = rate_test - rate_ctrl
    rel_lift = abs_lift / rate_ctrl if rate_ctrl > 0 else 0

    z, p = proportions_ztest([x_test, x_ctrl], [n_test, n_ctrl])
    ci_test = proportion_confint(x_test, n_test, alpha=0.05, method="normal")
    ci_ctrl = proportion_confint(x_ctrl, n_ctrl, alpha=0.05, method="normal")

    se_diff = np.sqrt(rate_test * (1 - rate_test) / n_test + rate_ctrl * (1 - rate_ctrl) / n_ctrl)
    z_crit = stats.norm.ppf(0.975)
    ci_diff = (abs_lift - z_crit * se_diff, abs_lift + z_crit * se_diff)

    return dict(
        n_test=n_test, n_ctrl=n_ctrl,
        x_test=int(x_test), x_ctrl=int(x_ctrl),
        rate_test=rate_test, rate_ctrl=rate_ctrl,
        abs_lift=abs_lift, rel_lift=rel_lift,
        p_value=p, z_stat=z,
        ci_test=ci_test, ci_ctrl=ci_ctrl, ci_diff=ci_diff
    )

s = compute_stats(df_filtered)

if s is None:
    st.warning("Not enough data in this segment for reliable statistics.")
    st.stop()

# ─────────────────────────────────────────────
# KPI Cards
# ─────────────────────────────────────────────
st.subheader("📊 Key Metrics")
col1, col2, col3, col4, col5 = st.columns(5)

col1.metric(
    "Test Completion Rate",
    f"{s['rate_test']:.2%}",
    help="% of Test clients who reached the confirm step"
)
col2.metric(
    "Control Completion Rate",
    f"{s['rate_ctrl']:.2%}",
    help="% of Control clients who reached the confirm step"
)
col3.metric(
    "Absolute Lift",
    f"{s['abs_lift']:+.2%}",
    delta=f"{s['abs_lift']:+.2%}",
    help="Difference in completion rate (Test − Control)"
)
col4.metric(
    "Relative Lift",
    f"{s['rel_lift']:+.2%}",
    delta=f"{'Above' if s['rel_lift'] > BUSINESS_THRESHOLD else 'Below'} 5% threshold",
    delta_color="normal" if s['rel_lift'] > BUSINESS_THRESHOLD else "inverse",
    help="Relative improvement vs Control"
)
col5.metric(
    "P-value",
    f"{s['p_value']:.4f}",
    delta="Significant ✅" if s["p_value"] < 0.05 else "Not significant ❌",
    delta_color="normal" if s["p_value"] < 0.05 else "inverse"
)

st.markdown("---")

# ─────────────────────────────────────────────
# Business verdict
# ─────────────────────────────────────────────
sig = s["p_value"] < 0.05
exceeds = s["rel_lift"] > BUSINESS_THRESHOLD

if sig and exceeds:
    verdict_color = "#065F46"
    verdict_bg = "#D1FAE5"
    verdict_icon = "✅"
    verdict_text = f"Lift of {s['rel_lift']:+.1%} is statistically significant (p={s['p_value']:.4f}) and exceeds the 5% business threshold. **Recommend rolling out the new UX.**"
elif sig and not exceeds:
    verdict_color = "#92400E"
    verdict_bg = "#FEF3C7"
    verdict_icon = "⚠️"
    verdict_text = f"Lift is statistically significant (p={s['p_value']:.4f}) but the relative lift of {s['rel_lift']:+.1%} falls below the 5% threshold. Effect too small to justify rollout cost."
elif not sig and exceeds:
    verdict_color = "#1E3A8A"
    verdict_bg = "#DBEAFE"
    verdict_icon = "🔍"
    verdict_text = f"Relative lift of {s['rel_lift']:+.1%} looks promising but is not statistically significant (p={s['p_value']:.4f}). Consider extending the test period."
else:
    verdict_color = "#7F1D1D"
    verdict_bg = "#FEE2E2"
    verdict_icon = "❌"
    verdict_text = f"No significant lift detected. Relative lift = {s['rel_lift']:+.1%}, p = {s['p_value']:.4f}. Do not roll out."

st.markdown(
    f"""
    <div style="background:{verdict_bg}; border-left: 5px solid {verdict_color};
                padding: 16px 20px; border-radius: 6px; margin-bottom: 16px;">
        <span style="font-size:1.4em;">{verdict_icon}</span>
        <strong style="color:{verdict_color}; font-size:1.05em;"> Business Verdict</strong><br>
        <span style="color:#1f2937;">{verdict_text}</span>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("---")

# ─────────────────────────────────────────────
# Charts row
# ─────────────────────────────────────────────
col_left, col_right = st.columns(2)

# ── Completion rate bar chart with CI ──
with col_left:
    st.subheader("Completion Rate — Test vs Control")
    fig_bar = go.Figure()
    for group, rate, ci in [
        ("Control", s["rate_ctrl"], s["ci_ctrl"]),
        ("Test", s["rate_test"], s["ci_test"])
    ]:
        fig_bar.add_trace(go.Bar(
            name=group,
            x=[group],
            y=[rate],
            error_y=dict(type="data", array=[ci[1] - rate], arrayminus=[rate - ci[0]], visible=True),
            marker_color=COLORS[group],
            text=f"{rate:.2%}",
            textposition="outside",
            textfont=dict(size=14, color="black")
        ))

    fig_bar.add_hline(
        y=s["rate_ctrl"],
        line_dash="dot", line_color="gray",
        annotation_text="Control baseline", annotation_position="top left"
    )
    fig_bar.update_layout(
        yaxis_tickformat=".0%",
        yaxis_title="Completion Rate",
        showlegend=True,
        plot_bgcolor="white",
        height=380,
        margin=dict(t=20, b=30)
    )
    st.plotly_chart(fig_bar, use_container_width=True)

# ── Funnel chart ──
with col_right:
    st.subheader("Funnel Drop-off by Step")
    step_rank = {step: i for i, step in enumerate(STEP_ORDER)}
    exp_map = df_filtered[["client_id", "Variation"]].drop_duplicates()
    df_web_exp = df_web.merge(exp_map, on="client_id", how="inner")
    df_web_exp["step_rank"] = df_web_exp["process_step"].map(step_rank)
    client_max = df_web_exp.groupby(["client_id", "Variation"])["step_rank"].max().reset_index()

    funnel_rows = []
    for group in ["Test", "Control"]:
        total = len(df_filtered[df_filtered["Variation"] == group])
        grp = client_max[client_max["Variation"] == group]
        for step, rank in step_rank.items():
            reached = (grp["step_rank"] >= rank).sum()
            funnel_rows.append({"Group": group, "Step": step, "Pct": reached / total if total > 0 else 0})

    df_funnel = pd.DataFrame(funnel_rows)

    fig_funnel = go.Figure()
    for group in ["Control", "Test"]:
        grp = df_funnel[df_funnel["Group"] == group]
        fig_funnel.add_trace(go.Bar(
            name=group,
            x=grp["Step"],
            y=grp["Pct"],
            marker_color=COLORS[group],
            text=[f"{v:.1%}" for v in grp["Pct"]],
            textposition="outside",
            textfont=dict(size=10)
        ))

    fig_funnel.update_layout(
        barmode="group",
        yaxis_tickformat=".0%",
        yaxis_title="% of Group Clients",
        xaxis_title="Funnel Step",
        plot_bgcolor="white",
        height=380,
        margin=dict(t=20, b=30)
    )
    st.plotly_chart(fig_funnel, use_container_width=True)

st.markdown("---")

# ─────────────────────────────────────────────
# Confidence interval for lift
# ─────────────────────────────────────────────
st.subheader("📐 Lift Confidence Interval")
fig_ci = go.Figure()
fig_ci.add_trace(go.Scatter(
    x=[s["ci_diff"][0], s["ci_diff"][1]],
    y=["Lift", "Lift"],
    mode="lines",
    line=dict(color="#2563EB", width=4),
    name="95% CI"
))
fig_ci.add_trace(go.Scatter(
    x=[s["abs_lift"]],
    y=["Lift"],
    mode="markers",
    marker=dict(size=14, color="#2563EB"),
    name=f"Estimate: {s['abs_lift']:+.2%}"
))
fig_ci.add_vline(x=0, line_dash="dash", line_color="gray", annotation_text="No effect")
fig_ci.add_vline(x=BUSINESS_THRESHOLD * s["rate_ctrl"],
                 line_dash="dot", line_color="orange",
                 annotation_text="Business threshold")
fig_ci.update_layout(
    xaxis_tickformat=".1%",
    xaxis_title="Absolute Lift in Completion Rate",
    height=200,
    showlegend=True,
    plot_bgcolor="white",
    margin=dict(t=10, b=30)
)
st.plotly_chart(fig_ci, use_container_width=True)

st.markdown("---")

# ─────────────────────────────────────────────
# Methodology note
# ─────────────────────────────────────────────
with st.expander("📘 Methodology Notes"):
    st.markdown(f"""
**Unit of analysis:** `client_id`

The experiment was randomized at client level*. All metrics are aggregated to one row per client before statistical testing.
Using `visitor_id` or `visit_id` as the analysis unit would treat correlated observations from the same client as independent,
artificially inflating the sample size and producing overstated statistical significance. Completion is also inherently a user-level outcome.

**Primary metric:** Binary completion flag — did the client reach the `confirm` step at least once during the test period?

**Statistical test:** Two-sided two-proportion z-test (α = 0.05)

**Sample sizes:**
- Test: {s['n_test']:,} clients ({s['x_test']:,} completions)
- Control: {s['n_ctrl']:,} clients ({s['x_ctrl']:,} completions)

**Business threshold:** Relative lift > 5% required to justify UX change cost.

***Reference:** Kohavi, Tang & Xu — *Trustworthy Online Controlled Experiments* (2020), Chapter 14: Choosing a Randomization Unit.
    """)

st.caption("Built with Streamlit · Analysis by Ngoc Ha Nguyen | LinkedIn: https://www.linkedin.com/in/ngoc-ha-nguyen/ · Data: Vanguard A/B Experiment Dataset")
