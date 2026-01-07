import os
import duckdb
import pandas as pd
import streamlit as st
from pathlib import Path
import subprocess
import sys




from launchlens.experimentation.ab_readout import run_readout

st.set_page_config(page_title="LaunchLens", layout="wide")

DB_PATH = "data/launchlens.duckdb"
EXPERIMENT_ID = "exp_checkout_v1"

st.title("LaunchLens")
st.caption("Product metrics + A/B readouts + SRM/guardrails (synthetic demo)")

# Sidebar
st.sidebar.header("Controls")
db_path = st.sidebar.text_input("DuckDB path", DB_PATH)
experiment_id = st.sidebar.text_input("Experiment ID", EXPERIMENT_ID)
st.sidebar.divider()
st.sidebar.subheader("Report")

report_out_dir = st.sidebar.text_input("Report output folder", "artifacts/reports")
report_filename = f"{experiment_id}_report.md"
report_path = Path(report_out_dir) / report_filename

if st.sidebar.button("Generate report (.md)"):
    Path(report_out_dir).mkdir(parents=True, exist_ok=True)
    # call the report generator using the same python env
    env = dict(**os.environ)
    env["PYTHONPATH"] = "src"
    subprocess.run(
        [sys.executable, "src/launchlens/experimentation/generate_report.py",

         "--db", db_path,
         "--experiment_id", experiment_id,
         "--out_dir", report_out_dir],
        check=True,
        env=env,
    )
    st.sidebar.success(f"Generated: {report_path}")

if report_path.exists():
    st.sidebar.download_button(
        label="Download report",
        data=report_path.read_text(encoding="utf-8"),
        file_name=report_filename,
        mime="text/markdown",
    )
else:
    st.sidebar.caption("Generate the report to enable download.")


con = duckdb.connect(db_path)

# --- SRM (user-level + session-level) ---
users = con.execute(
    """
    SELECT variant, COUNT(*) AS n_users
    FROM users
    WHERE experiment_id = ?
    GROUP BY 1
    """,
    [experiment_id],
).fetchdf()

sessions = con.execute(
    """
    SELECT variant, COUNT(*) AS n_sessions
    FROM fact_sessions
    WHERE experiment_id = ?
      AND is_experiment_period = TRUE
    GROUP BY 1
    """,
    [experiment_id],
).fetchdf()

def get_count(df: pd.DataFrame, col: str, label: str) -> int:
    sub = df[df["variant"] == label]
    if sub.empty:
        return 0
    return int(sub[col].iloc[0])

u_c = get_count(users, "n_users", "control")
u_t = get_count(users, "n_users", "treatment")
s_c = get_count(sessions, "n_sessions", "control")
s_t = get_count(sessions, "n_sessions", "treatment")

# Simple SRM p-value via chi-square against 50/50
import numpy as np
from scipy import stats

def srm_pval(nc, nt, expected_treat=0.5):
    total = nc + nt
    exp = np.array([total*(1-expected_treat), total*expected_treat], dtype=float)
    obs = np.array([nc, nt], dtype=float)
    chi2, p = stats.chisquare(f_obs=obs, f_exp=exp)
    return float(chi2), float(p)

chi_u, p_u = srm_pval(u_c, u_t, 0.5)
chi_s, p_s = srm_pval(s_c, s_t, 0.5)

# --- Guardrails ---
guard = con.execute(
    """
    SELECT
      variant,
      COUNT(*) AS sessions,
      AVG(has_click)::DOUBLE AS click_rate,
      AVG(has_add_to_cart)::DOUBLE AS atc_rate_per_session,
      AVG(has_purchase)::DOUBLE AS purchase_rate_per_session,
      AVG(revenue)::DOUBLE AS revenue_per_session,
      (SUM(has_click)::DOUBLE / NULLIF(SUM(has_impression), 0)) AS ctr,
      (SUM(has_add_to_cart)::DOUBLE / NULLIF(SUM(has_click), 0)) AS atc_rate_given_click
    FROM fact_sessions
    WHERE experiment_id = ?
      AND is_experiment_period = TRUE
    GROUP BY 1
    ORDER BY 1
    """,
    [experiment_id],
).fetchdf()

con.close()

# --- A/B Readout ---
readout = run_readout(db_path, experiment_id)

# Decision logic (simple demo): ship if purchase_rate_per_session p<0.05 and abs_diff>0
primary = readout[readout["metric"] == "purchase_rate_per_session"].iloc[0]
pval_primary = float(primary["p_value"])
abs_diff_primary = primary["abs_diff"]

# abs_diff_primary is a string like "0.132%" in our formatted output
abs_diff_num = float(abs_diff_primary.replace("%", "")) / 100.0

ship = (pval_primary < 0.05) and (abs_diff_num > 0)

# --- Layout ---
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Decision")
    if ship:
        st.success("Ship ✅")
    else:
        st.warning("Hold / Continue Experiment ⚠️")
    st.write("Primary metric:", "purchase_rate_per_session")
    st.write("Δ (T-C):", primary["abs_diff"], " | p-value:", primary["p_value"])
    st.caption("Decision rule (demo): ship if p<0.05 and lift>0")

with col2:
    st.subheader("SRM (User-level)")
    st.metric("Control users", f"{u_c:,}")
    st.metric("Treatment users", f"{u_t:,}")
    st.write(f"chi2={chi_u:.3f} | p={p_u:.4f}")
    st.caption("Primary SRM check should be user-level.")

with col3:
    st.subheader("SRM (Session-level)")
    st.metric("Control sessions", f"{s_c:,}")
    st.metric("Treatment sessions", f"{s_t:,}")
    st.write(f"chi2={chi_s:.3f} | p={p_s:.4f}")
    st.caption("Diagnostic only; can flag activity imbalance.")

st.divider()

st.subheader("Trends (Daily)")

con = duckdb.connect(db_path)
daily = con.execute(
    """
    SELECT
      event_date,
      variant,
      is_experiment_period,
      sessions,
      purchase_rate_per_session,
      revenue_per_session,
      ctr,
      atc_rate
    FROM daily_metrics
    WHERE experiment_id = ?
    ORDER BY event_date, variant
    """,
    [experiment_id],
).fetchdf()
con.close()

daily["event_date"] = pd.to_datetime(daily["event_date"])

cA, cB = st.columns(2)

with cA:
    st.caption("Purchase rate per session (daily)")
    chart_df = daily.pivot_table(index="event_date", columns="variant", values="purchase_rate_per_session")
    st.line_chart(chart_df)

with cB:
    st.caption("Revenue per session (daily)")
    chart_df = daily.pivot_table(index="event_date", columns="variant", values="revenue_per_session")
    st.line_chart(chart_df)

cC, cD = st.columns(2)

with cC:
    st.caption("CTR (daily)")
    chart_df = daily.pivot_table(index="event_date", columns="variant", values="ctr")
    st.line_chart(chart_df)

with cD:
    st.caption("ATC rate (daily)")
    chart_df = daily.pivot_table(index="event_date", columns="variant", values="atc_rate")
    st.line_chart(chart_df)

st.caption("Tip: Pre-period vs experiment period is encoded in is_experiment_period for diagnostics.")


c1, c2 = st.columns([1.4, 1.0])

with c1:
    st.subheader("A/B Readout (Experiment Period)")
    st.dataframe(readout, use_container_width=True)

with c2:
    st.subheader("Guardrails")
    st.dataframe(guard, use_container_width=True)

st.divider()

st.subheader("Notes")
st.write(
    """
- Data is synthetic but structured like real product telemetry (session funnel).
- LaunchLens surfaces SRM, guardrails, and experiment impact in one view.
- Next upgrades: CUPED improvement + anomaly detection + auto PDF report.
"""
)
