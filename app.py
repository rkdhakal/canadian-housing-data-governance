import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
import os
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Housing DQ Dashboard",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Dashboard colour palette */
    :root {
        --cmhc-dark:  #1F4E79;
        --cmhc-mid:   #2E75B6;
        --cmhc-light: #D6E4F0;
        --pass-clr:   #1a7a4a;
        --warn-clr:   #b8860b;
        --fail-clr:   #b22222;
        --pass-bg:    #d4edda;
        --warn-bg:    #fff3cd;
        --fail-bg:    #f8d7da;
    }

    /* Top header bar */
    header[data-testid="stHeader"] {
        background-color: var(--cmhc-dark);
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: var(--cmhc-light);
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] li,
    section[data-testid="stSidebar"] a {
        color: var(--cmhc-dark) !important;
    }

    /* Tab styling */
    button[data-baseweb="tab"] {
        font-size: 0.95rem;
        font-weight: 600;
        color: var(--cmhc-dark);
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        border-bottom: 3px solid var(--cmhc-mid) !important;
        color: var(--cmhc-mid) !important;
    }

    /* Metric cards */
    div[data-testid="metric-container"] {
        background-color: #f0f6fc;
        border: 1px solid #c0d8ef;
        border-radius: 8px;
        padding: 12px 16px;
    }
    div[data-testid="metric-container"] label {
        color: var(--cmhc-dark) !important;
        font-weight: 600;
    }

    /* Status badge helper classes */
    .badge-pass  { background:var(--pass-bg); color:var(--pass-clr);
                   border:1px solid var(--pass-clr); border-radius:4px;
                   padding:2px 8px; font-weight:700; font-size:0.82rem; }
    .badge-warn  { background:var(--warn-bg); color:var(--warn-clr);
                   border:1px solid var(--warn-clr); border-radius:4px;
                   padding:2px 8px; font-weight:700; font-size:0.82rem; }
    .badge-fail  { background:var(--fail-bg); color:var(--fail-clr);
                   border:1px solid var(--fail-clr); border-radius:4px;
                   padding:2px 8px; font-weight:700; font-size:0.82rem; }

    /* Callout box */
    .callout-box {
        background-color: #fff8e1;
        border-left: 5px solid #f9a825;
        border-radius: 4px;
        padding: 14px 18px;
        margin-top: 10px;
    }
    .callout-box strong { color: #b8860b; }

    /* Section headings */
    .section-heading {
        color: var(--cmhc-dark);
        font-size: 1.1rem;
        font-weight: 700;
        border-bottom: 2px solid var(--cmhc-mid);
        padding-bottom: 4px;
        margin-bottom: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

RAW_DATA_PATH          = os.path.join(BASE_DIR, "data", "raw", "cmhc_housing_starts_2018_2023.csv")
EXEC_SCORECARD_PATH    = os.path.join(BASE_DIR, "scorecard", "dq_execution_scorecard.csv")
SUMMARY_PATH           = os.path.join(BASE_DIR, "scorecard", "dq_scorecard_summary.csv")
BY_DIMENSION_PATH      = os.path.join(BASE_DIR, "scorecard", "dq_scorecard_by_dimension.csv")
BY_CDE_PATH            = os.path.join(BASE_DIR, "scorecard", "dq_scorecard_by_cde.csv")
EXCEPTIONS_PATH        = os.path.join(BASE_DIR, "data", "processed", "dq_exceptions.csv")

REQUIRED_COLUMNS = [
    "REF_DATE", "GEO", "GEO_CODE", "DWELLING_TYPE",
    "INTENDED_MARKET", "HOUSING_STARTS", "AVERAGE_PRICE_CAD",
]

GITHUB_REPO    = "https://github.com/rkdhakal/cmhc-housing-data-governance"
STREAMLIT_URL  = "https://cmhc-housing-data-governance-zaslgtkfkxi5n5agrz87th.streamlit.app"

# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data
def load_raw_data():
    if not os.path.exists(RAW_DATA_PATH):
        return None
    return pd.read_csv(RAW_DATA_PATH, low_memory=False)


@st.cache_data
def load_exec_scorecard():
    if not os.path.exists(EXEC_SCORECARD_PATH):
        return None
    return pd.read_csv(EXEC_SCORECARD_PATH)


@st.cache_data
def load_summary():
    if not os.path.exists(SUMMARY_PATH):
        return None
    return pd.read_csv(SUMMARY_PATH)


@st.cache_data
def load_by_dimension():
    if not os.path.exists(BY_DIMENSION_PATH):
        return None
    return pd.read_csv(BY_DIMENSION_PATH)


@st.cache_data
def load_by_cde():
    if not os.path.exists(BY_CDE_PATH):
        return None
    return pd.read_csv(BY_CDE_PATH)


@st.cache_data
def load_exceptions():
    if not os.path.exists(EXCEPTIONS_PATH):
        return None
    return pd.read_csv(EXCEPTIONS_PATH, low_memory=False)


# ── Colour helpers ────────────────────────────────────────────────────────────

def score_color(val: float) -> str:
    if val >= 99:
        return "#1a7a4a"
    if val >= 95:
        return "#b8860b"
    return "#b22222"


def status_color(status: str) -> str:
    mapping = {"PASS": "#1a7a4a", "WARN": "#b8860b", "FAIL": "#b22222"}
    return mapping.get(str(status).upper(), "#555555")


def badge_html(status: str) -> str:
    cls = {"PASS": "badge-pass", "WARN": "badge-warn", "FAIL": "badge-fail"}.get(
        str(status).upper(), "badge-warn"
    )
    return f'<span class="{cls}">{status}</span>'


# ── DQ Rule implementations (for Tab 4) ──────────────────────────────────────
# These domain values must stay in sync with dq_engine.py
_VALID_GEO_CODES = {"ON","BC","AB","QC","MB","SK","NS","NB","NL","PE","NT","YT","NU"}
_VALID_DWELLING  = {"Single-Detached","Semi-Detached","Row House",
                    "Apartment - 5+ storeys","Apartment - Under 5 storeys"}
_VALID_MARKETS   = {"Homeowner","Rental","Condominium"}
_VALID_STATUS    = {"","E","F","r"}
_GEO_MAPPING = {
    "Ontario":"ON","British Columbia":"BC","Alberta":"AB","Quebec":"QC",
    "Manitoba":"MB","Saskatchewan":"SK","Nova Scotia":"NS","New Brunswick":"NB",
    "Newfoundland and Labrador":"NL","Prince Edward Island":"PE",
    "Northwest Territories":"NT","Yukon":"YT","Nunavut":"NU",
}


def run_dq_rules(df: pd.DataFrame):
    """
    Apply all 15 DQ rules (identical logic to dq_engine.py) to an uploaded dataframe.
    Returns (scorecard_df, n_unique_failed_records).
    """
    import numpy as np
    total = len(df)
    results = []
    failed_indices: set = set()

    def record(rule_id, rule_name, dimension, cde, description, severity, fail_mask):
        arr = fail_mask.values if hasattr(fail_mask, "values") else np.array(fail_mask)
        failed = int(arr.sum())
        passed = total - failed
        pass_rate = round(100 * passed / total, 2) if total > 0 else 0.0
        status = "PASS" if pass_rate == 100 else ("WARN" if pass_rate >= 95 else "FAIL")
        failed_indices.update(df.index[arr].tolist())
        results.append({
            "Rule_ID": rule_id, "Rule_Name": rule_name,
            "DQ_Dimension": dimension, "CDE_Affected": cde,
            "Description": description, "Severity": severity,
            "Total_Records": total, "Records_Passed": passed,
            "Records_Failed": failed, "Pass_Rate_Pct": pass_rate,
            "Status": status,
            "Remediation_Action": "Review flagged records and correct source data.",
        })

    # STATUS helper (column may be absent in user uploads)
    status_col = df["STATUS"].fillna("") if "STATUS" in df.columns else pd.Series([""] * total, index=df.index)

    # DQ-001: HOUSING_STARTS completeness
    record("DQ-001", "Housing Starts Completeness", "Completeness", "HOUSING_STARTS",
           "HOUSING_STARTS must not be NULL.", "High",
           df["HOUSING_STARTS"].isnull())

    # DQ-002: HOUSING_STARTS non-negative
    record("DQ-002", "Housing Starts Non-Negative", "Validity", "HOUSING_STARTS",
           "HOUSING_STARTS must be >= 0. Negative values are physically impossible.", "Critical",
           df["HOUSING_STARTS"].fillna(0) < 0)

    # DQ-003: AVERAGE_PRICE_CAD completeness (non-suppressed records only)
    record("DQ-003", "Average Price Completeness", "Completeness", "AVERAGE_PRICE_CAD",
           "AVERAGE_PRICE_CAD must not be NULL on non-suppressed records.", "Medium",
           df["AVERAGE_PRICE_CAD"].isnull() & (status_col != "F"))

    # DQ-004: AVERAGE_PRICE_CAD non-negative
    record("DQ-004", "Average Price Non-Negative", "Validity", "AVERAGE_PRICE_CAD",
           "AVERAGE_PRICE_CAD must be > 0. Negative prices are invalid.", "Critical",
           df["AVERAGE_PRICE_CAD"].fillna(0) < 0)

    # DQ-005: AVERAGE_PRICE_CAD ceiling
    record("DQ-005", "Average Price Ceiling Check", "Validity", "AVERAGE_PRICE_CAD",
           "AVERAGE_PRICE_CAD must not exceed $2,000,000.", "Medium",
           df["AVERAGE_PRICE_CAD"].fillna(0) > 2_000_000)

    # DQ-006: GEO_CODE referential integrity
    geo_code = df["GEO_CODE"] if "GEO_CODE" in df.columns else pd.Series([""] * total, index=df.index)
    record("DQ-006", "GEO_CODE Referential Integrity", "Validity", "GEO_CODE",
           "GEO_CODE must be a valid Canadian province/territory code.", "High",
           ~geo_code.isin(_VALID_GEO_CODES))

    # DQ-007: DWELLING_TYPE domain validity
    record("DQ-007", "Dwelling Type Domain Validity", "Validity", "DWELLING_TYPE",
           "DWELLING_TYPE must be one of 5 approved categories.", "High",
           ~df["DWELLING_TYPE"].isin(_VALID_DWELLING))

    # DQ-008: INTENDED_MARKET domain validity
    record("DQ-008", "Intended Market Domain Validity", "Validity", "INTENDED_MARKET",
           "INTENDED_MARKET must be one of: Homeowner, Rental, Condominium.", "High",
           ~df["INTENDED_MARKET"].isin(_VALID_MARKETS))

    # DQ-009: REF_DATE format YYYY-MM
    record("DQ-009", "Reference Date Format", "Validity", "REF_DATE",
           "REF_DATE must follow YYYY-MM format.", "Medium",
           ~df["REF_DATE"].astype(str).str.match(r"^\d{4}-\d{2}$"))

    # DQ-010: Grain uniqueness
    grain_cols = [c for c in ["REF_DATE","GEO_CODE","DWELLING_TYPE","INTENDED_MARKET"] if c in df.columns]
    dup_mask = df.duplicated(subset=grain_cols, keep=False) if grain_cols else pd.Series([False]*total, index=df.index)
    record("DQ-010", "Grain Uniqueness", "Uniqueness",
           "REF_DATE+GEO_CODE+DWELLING_TYPE+INTENDED_MARKET",
           "Each grain combination (REF_DATE + GEO_CODE + DWELLING_TYPE + INTENDED_MARKET) must be unique.", "High",
           dup_mask)

    # DQ-011: REF_DATE not future
    current_month = datetime.now().strftime("%Y-%m")
    record("DQ-011", "Reference Date Not Future", "Validity", "REF_DATE",
           "REF_DATE must not be after the current month.", "Medium",
           df["REF_DATE"].astype(str) > current_month)

    # DQ-012: STATUS code validity
    record("DQ-012", "Status Code Validity", "Validity", "STATUS",
           "STATUS must be blank, 'E', 'F', or 'r'.", "Low",
           ~status_col.isin(_VALID_STATUS))

    # DQ-013: HOUSING_STARTS accuracy — statistical range (province z-score)
    if "GEO_CODE" in df.columns and df["HOUSING_STARTS"].notna().any():
        prov_hs = (
            df[df["HOUSING_STARTS"].notna()]
            .groupby("GEO_CODE")["HOUSING_STARTS"]
            .agg(["mean","std"]).reset_index()
            .rename(columns={"mean":"hs_mean","std":"hs_std"})
        )
        df_013 = df.merge(prov_hs, on="GEO_CODE", how="left")
        mask_013 = (
            (df_013["HOUSING_STARTS"] > 20_000) |
            (df_013["HOUSING_STARTS"] > df_013["hs_mean"] + 3 * df_013["hs_std"])
        ).fillna(False)
        mask_013.index = df.index
    else:
        mask_013 = pd.Series([False]*total, index=df.index)
    record("DQ-013", "Housing Starts Accuracy — Statistical Range", "Accuracy", "HOUSING_STARTS",
           "HOUSING_STARTS must not exceed 20,000 or mean + 3 std dev for its province.", "High",
           mask_013)

    # DQ-014: AVERAGE_PRICE_CAD accuracy — statistical range
    if "GEO_CODE" in df.columns and df["AVERAGE_PRICE_CAD"].notna().any():
        prov_pr = (
            df[df["AVERAGE_PRICE_CAD"].notna()]
            .groupby("GEO_CODE")["AVERAGE_PRICE_CAD"]
            .agg(["mean","std"]).reset_index()
            .rename(columns={"mean":"price_mean","std":"price_std"})
        )
        df_014 = df.merge(prov_pr, on="GEO_CODE", how="left")
        mask_014 = (
            df_014["AVERAGE_PRICE_CAD"].notna() &
            (
                (df_014["AVERAGE_PRICE_CAD"] < 100_000) |
                (df_014["AVERAGE_PRICE_CAD"] > 3_000_000) |
                (df_014["AVERAGE_PRICE_CAD"] > df_014["price_mean"] + 3 * df_014["price_std"])
            )
        ).fillna(False)
        mask_014.index = df.index
    else:
        mask_014 = pd.Series([False]*total, index=df.index)
    record("DQ-014", "Average Price Accuracy — Statistical Range", "Accuracy", "AVERAGE_PRICE_CAD",
           "AVERAGE_PRICE_CAD must be between $100,000 and $3,000,000 and not exceed mean + 3 std dev for its province.", "High",
           mask_014)

    # DQ-015: GEO and GEO_CODE consistency
    if "GEO" in df.columns and "GEO_CODE" in df.columns:
        expected = df["GEO"].map(_GEO_MAPPING)
        mask_015 = expected.notna() & (df["GEO_CODE"] != expected)
    else:
        mask_015 = pd.Series([False]*total, index=df.index)
    record("DQ-015", "GEO and GEO_CODE Consistency", "Consistency", "GEO + GEO_CODE",
           "GEO (full province name) and GEO_CODE (2-letter code) must always refer to the same province.", "Critical",
           mask_015)

    return pd.DataFrame(results), len(failed_indices)


def compute_summary_from_scorecard(scorecard_df: pd.DataFrame, total_records: int,
                                    n_unique_failed: int = None) -> dict:
    """Derive summary metrics from a run_dq_rules() result."""
    n_pass = int((scorecard_df["Status"] == "PASS").sum())
    n_warn = int((scorecard_df["Status"] == "WARN").sum())
    n_fail = int((scorecard_df["Status"] == "FAIL").sum())
    total_failed = int(scorecard_df["Records_Failed"].sum())
    overall_score = round(scorecard_df["Pass_Rate_Pct"].mean(), 1)

    def grade(s):
        if s >= 99:
            return "A"
        if s >= 95:
            return "B"
        if s >= 90:
            return "C"
        return "D"

    dim_scores = {}
    for dim in ["Completeness", "Validity", "Uniqueness", "Accuracy", "Consistency"]:
        sub = scorecard_df[scorecard_df["DQ_Dimension"] == dim]
        dim_scores[dim] = round(sub["Pass_Rate_Pct"].mean(), 1) if len(sub) > 0 else 100.0

    # Use unique failed record count (not sum of rule failures) to avoid >100% clean bug
    n_failed_unique = n_unique_failed if n_unique_failed is not None else total_failed
    clean_pct = round(100 * (total_records - n_failed_unique) / total_records, 1) if total_records > 0 else 100.0

    return {
        "total_records": total_records,
        "total_rules": len(scorecard_df),
        "n_pass": n_pass,
        "n_warn": n_warn,
        "n_fail": n_fail,
        "total_failed": total_failed,
        "overall_score": overall_score,
        "overall_grade": grade(overall_score),
        "clean_pct": clean_pct,
        "dim_scores": dim_scores,
    }


# ── Shared chart builders ─────────────────────────────────────────────────────

def dim_bar_chart(dim_df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of dimension scores."""
    df_sorted = dim_df.sort_values("Dimension_Score", ascending=True)
    colors = [score_color(v) for v in df_sorted["Dimension_Score"]]
    fig = go.Figure(
        go.Bar(
            x=df_sorted["Dimension_Score"],
            y=df_sorted["DQ_Dimension"],
            orientation="h",
            marker_color=colors,
            text=[f"{v:.1f}%" for v in df_sorted["Dimension_Score"]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Score: %{x:.1f}%<extra></extra>",
        )
    )
    fig.add_vline(x=99, line_dash="dot", line_color="#1a7a4a")
    fig.add_vline(x=95, line_dash="dot", line_color="#b8860b")
    # Stagger vertically so the two labels don't overlap
    fig.add_annotation(
        x=99, y=1.13, yref="paper", text="99% target",
        showarrow=False, font=dict(color="#1a7a4a", size=10), xanchor="center",
    )
    fig.add_annotation(
        x=95, y=1.04, yref="paper", text="95% warn",
        showarrow=False, font=dict(color="#b8860b", size=10), xanchor="center",
    )
    fig.update_layout(
        title="DQ Dimension Scores",
        xaxis=dict(range=[0, 116], title="Pass Rate (%)"),
        yaxis=dict(title=""),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial", size=13),
        height=340,
        margin=dict(l=20, r=90, t=60, b=20),
    )
    return fig


def rule_bar_chart(scorecard_df: pd.DataFrame) -> go.Figure:
    """Vertical bar chart of pass rate per rule, colour-coded by status."""
    df_s = scorecard_df.copy()
    colors = [status_color(s) for s in df_s["Status"]]
    fig = go.Figure(
        go.Bar(
            x=df_s["Rule_ID"],
            y=df_s["Pass_Rate_Pct"],
            marker_color=colors,
            text=[f"{v:.1f}%" for v in df_s["Pass_Rate_Pct"]],
            textposition="outside",
            customdata=df_s[["Rule_Name", "Status", "Records_Failed"]].values,
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Rule: %{customdata[0]}<br>"
                "Status: %{customdata[1]}<br>"
                "Pass Rate: %{y:.2f}%<br>"
                "Failed: %{customdata[2]:,}<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=99, line_dash="dot", line_color="#1a7a4a")
    fig.add_hline(y=95, line_dash="dot", line_color="#b8860b")
    # yanchor="bottom" floats text above the 99 line; yanchor="top" floats below the 95 line
    fig.add_annotation(
        x=1.01, xref="paper", y=99, yref="y",
        text="99% target", showarrow=False,
        font=dict(color="#1a7a4a", size=10), xanchor="left", yanchor="bottom",
    )
    fig.add_annotation(
        x=1.01, xref="paper", y=95, yref="y",
        text="95% warn", showarrow=False,
        font=dict(color="#b8860b", size=10), xanchor="left", yanchor="top",
    )
    fig.update_layout(
        title="Pass Rate per DQ Rule",
        xaxis=dict(title="Rule ID", tickangle=-30),
        yaxis=dict(range=[0, 112], title="Pass Rate (%)"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial", size=12),
        height=400,
        margin=dict(l=20, r=60, t=50, b=70),
    )
    return fig


def status_donut(n_pass: int, n_warn: int, n_fail: int) -> go.Figure:
    labels = ["PASS", "WARN", "FAIL"]
    values = [n_pass, n_warn, n_fail]
    colors = ["#1a7a4a", "#b8860b", "#b22222"]
    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.55,
            marker_colors=colors,
            textinfo="label+value",
            hovertemplate="<b>%{label}</b>: %{value} rules (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(
        title="Rules by Status",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15),
        height=320,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="white",
    )
    return fig


def dim_bar_from_dict(dim_scores: dict) -> go.Figure:
    """Build dimension bar chart from a plain dict (for Tab 4)."""
    df_tmp = pd.DataFrame(
        [{"DQ_Dimension": k, "Dimension_Score": v} for k, v in dim_scores.items()]
    )
    return dim_bar_chart(df_tmp)


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar():
    summary = load_summary()
    scorecard_date = "N/A"
    if summary is not None and "Scorecard_Date" in summary.columns:
        scorecard_date = str(summary["Scorecard_Date"].iloc[0])

    st.sidebar.markdown(
        f"""
        <h2 style="color:#1F4E79;margin-bottom:2px;">🏠 Housing DQ Dashboard</h2>
        <p style="color:#2E75B6;font-size:0.85rem;margin-top:0;">
            Data Governance Portfolio Project
        </p>
        <hr style="border-color:#2E75B6;">
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("**Author:** Ram Krishna Dhakal")
    st.sidebar.markdown("**Dataset:** CMHC-format Housing Starts (synthetic)")
    st.sidebar.markdown("**Records:** 10,800 | **Years:** 2018–2023")
    st.sidebar.markdown("**Coverage:** 10 provinces")
    st.sidebar.markdown(f"**Last DQ Run:** `{scorecard_date}`")

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"🔗 [GitHub Repo]({GITHUB_REPO})")

    with st.sidebar.expander("ℹ️ About this project"):
        st.write(
            "This dashboard presents a Canadian housing data quality framework "
            "built on synthetic CMHC-format Housing Starts data (2018–2023). "
            "Fifteen DQ rules spanning five ISO-aligned dimensions "
            "(Completeness, Validity, Accuracy, Consistency, Uniqueness) "
            "are applied to surface data quality issues and guide remediation. "
            "Designed as a portfolio project for a data governance analyst role."
        )


# ── Tab 1 — Executive Scorecard ───────────────────────────────────────────────

def tab_executive():
    summary    = load_summary()
    dim_df     = load_by_dimension()
    scorecard  = load_exec_scorecard()

    if summary is None:
        st.error(f"Summary file not found: `{SUMMARY_PATH}`")
        return
    if dim_df is None:
        st.error(f"Dimension scorecard not found: `{BY_DIMENSION_PATH}`")
        return
    if scorecard is None:
        st.error(f"Execution scorecard not found: `{EXEC_SCORECARD_PATH}`")
        return

    row = summary.iloc[0]

    total_records   = int(row.get("Total_Records", 0))
    n_pass          = int(row.get("Rules_PASS", 0))
    n_warn          = int(row.get("Rules_WARN", 0))
    n_fail          = int(row.get("Rules_FAIL", 0))
    total_failures  = int(row.get("Total_Rule_Failures", 0))
    overall_score   = float(row.get("Overall_DQ_Score_Pct", 0))
    overall_grade   = str(row.get("Overall_Grade", ""))
    recommended     = str(row.get("Recommended_Action", ""))
    # Use unique failed records (not sum of rule failures) — same method as Run on Your Data tab
    exc_df_tmp = load_exceptions()
    n_unique_failed = exc_df_tmp["_record_id"].nunique() if exc_df_tmp is not None and "_record_id" in exc_df_tmp.columns else total_failures
    clean_pct = round(100 * (total_records - n_unique_failed) / total_records, 1) \
                if total_records > 0 else 100.0

    # ── Metric cards ──
    st.markdown('<p class="section-heading">Overall Data Quality Metrics</p>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Overall DQ Score", f"{overall_score:.1f}%", f"Grade: {overall_grade}")
    c2.metric("Rules Passed ✅", n_pass, f"of {n_pass + n_warn + n_fail} rules")
    c3.metric("Rules Warning ⚠️", n_warn)
    c4.metric("Total Rule Failures 🔴", f"{total_failures:,}")
    c5.metric("Clean Records %", f"{clean_pct:.1f}%")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts row 1 ──
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.plotly_chart(dim_bar_chart(dim_df), use_container_width=True, key="tab1_dim_bar")

    with col_right:
        st.plotly_chart(status_donut(n_pass, n_warn, n_fail), use_container_width=True, key="tab1_donut")

    # ── Rule bar chart ──
    st.plotly_chart(rule_bar_chart(scorecard), use_container_width=True, key="tab1_rule_bar")

    # ── Recommended action callout ──
    if recommended and recommended.lower() not in ("nan", "none", ""):
        st.markdown(
            f'<div class="callout-box">'
            f'<strong>Recommended Action:</strong> {recommended}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── CDE table ──
    cde_df = load_by_cde()
    if cde_df is not None:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<p class="section-heading">Data Quality by Critical Data Element (CDE)</p>',
                    unsafe_allow_html=True)

        def grade_color(g):
            mapping = {"A": "#d4edda", "B": "#fff3cd", "C": "#f8d7da", "D": "#f8d7da"}
            return mapping.get(str(g).upper(), "")

        styled = cde_df.style.apply(
            lambda col: [
                f"background-color: {grade_color(v)}" if col.name == "CDE_Grade" else ""
                for v in col
            ],
            axis=0,
        ).format({"Avg_Pass_Rate": "{:.1f}%", "Total_Failed_Records": "{:,}"})

        st.dataframe(styled, use_container_width=True, hide_index=True)


# ── Tab 2 — DQ Rules ──────────────────────────────────────────────────────────

def tab_dq_rules():
    scorecard = load_exec_scorecard()
    if scorecard is None:
        st.error(f"Execution scorecard not found: `{EXEC_SCORECARD_PATH}`")
        return

    st.markdown('<p class="section-heading">DQ Rule Catalogue</p>', unsafe_allow_html=True)

    # ── Filters ──
    f1, f2, f3 = st.columns(3)
    all_dims = ["All"] + sorted(scorecard["DQ_Dimension"].dropna().unique().tolist())
    all_sevs = ["All"] + sorted(scorecard["Severity"].dropna().unique().tolist())
    all_stat = ["All"] + sorted(scorecard["Status"].dropna().unique().tolist())

    sel_dim = f1.selectbox("Filter by Dimension", all_dims)
    sel_sev = f2.selectbox("Filter by Severity", all_sevs)
    sel_sta = f3.selectbox("Filter by Status", all_stat)

    filtered = scorecard.copy()
    if sel_dim != "All":
        filtered = filtered[filtered["DQ_Dimension"] == sel_dim]
    if sel_sev != "All":
        filtered = filtered[filtered["Severity"] == sel_sev]
    if sel_sta != "All":
        filtered = filtered[filtered["Status"] == sel_sta]

    st.markdown(f"**Showing {len(filtered)} of {len(scorecard)} rules**")

    # ── Styled dataframe ──
    display_cols = [
        "Rule_ID", "Rule_Name", "DQ_Dimension", "Severity",
        "Pass_Rate_Pct", "Records_Failed", "Status",
    ]
    display_df = filtered[display_cols].copy()

    def color_status_row(row):
        bg = {"PASS": "#d4edda", "WARN": "#fff3cd", "FAIL": "#f8d7da"}.get(
            str(row["Status"]).upper(), ""
        )
        return [f"background-color: {bg}"] * len(row)

    styled = (
        display_df.style
        .apply(color_status_row, axis=1)
        .format({"Pass_Rate_Pct": "{:.2f}%", "Records_Failed": "{:,}"})
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Rule expanders ──
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<p class="section-heading">Rule Details</p>', unsafe_allow_html=True)
    for _, rule_row in filtered.iterrows():
        badge = badge_html(str(rule_row.get("Status", "")))
        with st.expander(
            f"**{rule_row['Rule_ID']}** — {rule_row['Rule_Name']}  "
            f"({rule_row['DQ_Dimension']} | {rule_row['Severity']})"
        ):
            col_a, col_b = st.columns(2)
            col_a.markdown(f"**Status:** {badge}", unsafe_allow_html=True)
            col_b.markdown(f"**Pass Rate:** `{rule_row['Pass_Rate_Pct']:.2f}%`")
            st.markdown(f"**Description:** {rule_row.get('Description', 'N/A')}")
            st.markdown(f"**Remediation:** {rule_row.get('Remediation_Action', 'N/A')}")
            col_x, col_y = st.columns(2)
            col_x.markdown(f"**Records Failed:** `{int(rule_row['Records_Failed']):,}`")
            col_y.markdown(f"**CDE Affected:** `{rule_row.get('CDE_Affected', 'N/A')}`")

    # ── Download ──
    st.markdown("<br>", unsafe_allow_html=True)
    csv_bytes = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Download filtered rules as CSV",
        data=csv_bytes,
        file_name="filtered_dq_rules.csv",
        mime="text/csv",
    )


# ── Tab 3 — Exception Explorer ────────────────────────────────────────────────

def tab_exceptions():
    exc_df = load_exceptions()
    if exc_df is None:
        st.error(f"Exceptions file not found: `{EXCEPTIONS_PATH}`")
        return

    st.markdown('<p class="section-heading">DQ Exception Explorer</p>', unsafe_allow_html=True)

    # ── Filters ──
    f1, f2, f3, f4 = st.columns(4)
    all_dims  = ["All"] + sorted(exc_df["_dimension"].dropna().unique().tolist())
    all_rules = ["All"] + sorted(exc_df["_rule_id"].dropna().unique().tolist())

    geo_col = "GEO_CODE" if "GEO_CODE" in exc_df.columns else None
    dwl_col = "DWELLING_TYPE" if "DWELLING_TYPE" in exc_df.columns else None

    all_geos = (["All"] + sorted(exc_df[geo_col].dropna().unique().tolist())) if geo_col else ["All"]
    all_dwls = (["All"] + sorted(exc_df[dwl_col].dropna().unique().tolist())) if dwl_col else ["All"]

    sel_dim  = f1.selectbox("DQ Dimension",  all_dims,  key="exc_dim")
    sel_rule = f2.selectbox("Rule ID",        all_rules, key="exc_rule")
    sel_geo  = f3.selectbox("Province (GEO_CODE)", all_geos, key="exc_geo")
    sel_dwl  = f4.selectbox("Dwelling Type",  all_dwls,  key="exc_dwl")

    filtered = exc_df.copy()
    if sel_dim  != "All": filtered = filtered[filtered["_dimension"] == sel_dim]
    if sel_rule != "All": filtered = filtered[filtered["_rule_id"]   == sel_rule]
    if sel_geo  != "All" and geo_col: filtered = filtered[filtered[geo_col] == sel_geo]
    if sel_dwl  != "All" and dwl_col: filtered = filtered[filtered[dwl_col] == sel_dwl]

    n_exc   = len(filtered)
    n_rules = filtered["_rule_id"].nunique() if "_rule_id" in filtered.columns else 0

    st.markdown(
        f'<div style="background:#f0f6fc;border-left:4px solid #2E75B6;'
        f'padding:10px 16px;border-radius:4px;margin-bottom:12px;">'
        f'<strong>{n_exc:,} exceptions</strong> found across '
        f'<strong>{n_rules}</strong> rule(s)</div>',
        unsafe_allow_html=True,
    )

    # ── Charts ──
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        if geo_col and n_exc > 0:
            geo_counts = (
                filtered[geo_col].value_counts().head(10).reset_index()
            )
            geo_counts.columns = ["Province", "Failures"]
            fig_geo = px.bar(
                geo_counts, x="Failures", y="Province", orientation="h",
                title="Top Failing Provinces",
                color="Failures",
                color_continuous_scale=["#2E75B6", "#1F4E79"],
            )
            fig_geo.update_layout(
                yaxis=dict(autorange="reversed"),
                plot_bgcolor="white", paper_bgcolor="white",
                height=300, margin=dict(l=10, r=10, t=40, b=10),
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig_geo, use_container_width=True, key="tab3_geo_bar")
        else:
            st.info("No geographic data to display.")

    with chart_col2:
        if dwl_col and n_exc > 0:
            dwl_counts = (
                filtered[dwl_col].value_counts().reset_index()
            )
            dwl_counts.columns = ["Dwelling Type", "Failures"]
            fig_dwl = px.bar(
                dwl_counts, x="Dwelling Type", y="Failures",
                title="Failures by Dwelling Type",
                color="Failures",
                color_continuous_scale=["#2E75B6", "#1F4E79"],
            )
            fig_dwl.update_layout(
                plot_bgcolor="white", paper_bgcolor="white",
                height=300, margin=dict(l=10, r=10, t=40, b=60),
                coloraxis_showscale=False, xaxis_tickangle=-30,
            )
            st.plotly_chart(fig_dwl, use_container_width=True, key="tab3_dwl_bar")
        else:
            st.info("No dwelling type data to display.")

    # ── Paginated table ──
    display_cols = [c for c in [
        "REF_DATE", "GEO_CODE", "DWELLING_TYPE", "INTENDED_MARKET",
        "HOUSING_STARTS", "AVERAGE_PRICE_CAD",
        "_rule_id", "_dimension", "_severity", "_failure_reason",
    ] if c in filtered.columns]

    st.markdown('<p class="section-heading">Exception Records</p>', unsafe_allow_html=True)

    PAGE_SIZE = 100
    total_pages = max(1, (n_exc + PAGE_SIZE - 1) // PAGE_SIZE)
    if total_pages > 1:
        page = st.number_input(
            f"Page (1–{total_pages})", min_value=1, max_value=total_pages, value=1, step=1
        )
    else:
        page = 1

    start = (page - 1) * PAGE_SIZE
    end   = start + PAGE_SIZE
    page_df = filtered[display_cols].iloc[start:end]

    st.dataframe(page_df, use_container_width=True, hide_index=True)
    st.caption(f"Showing records {start+1}–{min(end, n_exc):,} of {n_exc:,}")

    # ── Download ──
    csv_bytes = filtered[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Download exceptions as CSV",
        data=csv_bytes,
        file_name="dq_exceptions_filtered.csv",
        mime="text/csv",
    )


# ── Tab 4 — Run on Your Data ──────────────────────────────────────────────────

def tab_run_your_data():
    st.markdown('<p class="section-heading">Run DQ Rules on Your Own Dataset</p>',
                unsafe_allow_html=True)

    # ── Sample template download ──
    template_df = pd.DataFrame(columns=REQUIRED_COLUMNS + ["STATUS"])
    template_csv = template_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Download sample CSV template",
        data=template_csv,
        file_name="cmhc_template.csv",
        mime="text/csv",
    )

    st.markdown("---")

    uploaded = st.file_uploader(
        "Upload a CSV file in the CMHC Housing Starts format",
        type=["csv"],
        help=(
            f"Required columns: {', '.join(REQUIRED_COLUMNS)}"
        ),
    )

    if uploaded is None:
        st.info(
            "Upload a CSV to validate it against the 15 DQ rules. "
            f"Required columns: `{', '.join(REQUIRED_COLUMNS)}`."
        )
        return

    try:
        user_df = pd.read_csv(uploaded, low_memory=False)
    except Exception as e:
        st.error(f"Could not read the uploaded file: {e}")
        return

    # ── Column validation ──
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in user_df.columns]
    if missing_cols:
        st.error(
            f"The uploaded file is missing the following required columns: "
            f"`{'`, `'.join(missing_cols)}`\n\n"
            f"Please download the sample template above to see the expected format."
        )
        return

    st.success(
        f"File accepted — {len(user_df):,} records, "
        f"{len(user_df.columns)} columns detected."
    )

    with st.spinner("Running 15 DQ rules…"):
        result_scorecard, n_unique_failed = run_dq_rules(user_df)
        summary_dict = compute_summary_from_scorecard(result_scorecard, len(user_df), n_unique_failed)

    st.markdown("---")
    st.markdown('<p class="section-heading">Your DQ Scorecard</p>', unsafe_allow_html=True)

    # ── Metric cards ──
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Overall DQ Score",    f"{summary_dict['overall_score']:.1f}%",
              f"Grade: {summary_dict['overall_grade']}")
    c2.metric("Rules Passed ✅",      summary_dict["n_pass"],
              f"of {summary_dict['total_rules']} rules")
    c3.metric("Rules Warning ⚠️",    summary_dict["n_warn"])
    c4.metric("Total Rule Failures 🔴", f"{summary_dict['total_failed']:,}")
    c5.metric("Clean Records %",     f"{summary_dict['clean_pct']:.1f}%")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts ──
    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.plotly_chart(
            dim_bar_from_dict(summary_dict["dim_scores"]),
            use_container_width=True,
            key="tab4_dim_bar",
        )
    with col_r:
        st.plotly_chart(
            status_donut(
                summary_dict["n_pass"],
                summary_dict["n_warn"],
                summary_dict["n_fail"],
            ),
            use_container_width=True,
            key="tab4_donut",
        )

    st.plotly_chart(rule_bar_chart(result_scorecard), use_container_width=True, key="tab4_rule_bar")

    # ── Rule detail table ──
    st.markdown('<p class="section-heading">Rule-Level Results</p>', unsafe_allow_html=True)

    def color_row(row):
        bg = {"PASS": "#d4edda", "WARN": "#fff3cd", "FAIL": "#f8d7da"}.get(
            str(row["Status"]).upper(), ""
        )
        return [f"background-color: {bg}"] * len(row)

    display_cols = [
        "Rule_ID", "Rule_Name", "DQ_Dimension", "Severity",
        "Pass_Rate_Pct", "Records_Failed", "Status",
    ]
    styled_sc = (
        result_scorecard[display_cols].style
        .apply(color_row, axis=1)
        .format({"Pass_Rate_Pct": "{:.2f}%", "Records_Failed": "{:,}"})
    )
    st.dataframe(styled_sc, use_container_width=True, hide_index=True)

    # ── Download results ──
    csv_bytes = result_scorecard.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Download DQ scorecard as CSV",
        data=csv_bytes,
        file_name="your_dq_scorecard.csv",
        mime="text/csv",
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    render_sidebar()

    tabs = st.tabs([
        "📊 Executive Scorecard",
        "📋 DQ Rules",
        "🔍 Exception Explorer",
        "📁 Run on Your Data",
    ])

    with tabs[0]:
        tab_executive()

    with tabs[1]:
        tab_dq_rules()

    with tabs[2]:
        tab_exceptions()

    with tabs[3]:
        tab_run_your_data()


if __name__ == "__main__":
    main()


