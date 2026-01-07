from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

from launchlens.experimentation.ab_readout import run_readout


def _get_count(df: pd.DataFrame, col: str, label: str) -> int:
    sub = df[df["variant"] == label]
    if sub.empty:
        return 0
    return int(sub[col].iloc[0])


def _srm_pval(nc: int, nt: int, expected_treat: float = 0.5) -> tuple[float, float]:
    total = nc + nt
    exp = np.array([total * (1 - expected_treat), total * expected_treat], dtype=float)
    obs = np.array([nc, nt], dtype=float)
    chi2, p = stats.chisquare(f_obs=obs, f_exp=exp)
    return float(chi2), float(p)


def _table_md(df: pd.DataFrame) -> str:
    # Markdown table without extra deps
    return df.to_markdown(index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=str, default="data/launchlens.duckdb")
    ap.add_argument("--experiment_id", type=str, default="exp_checkout_v1")
    ap.add_argument("--expected_treatment_share", type=float, default=0.50)
    ap.add_argument("--out_dir", type=str, default="artifacts/reports")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(args.db)

    # ---------- SRM ----------
    users = con.execute(
        """
        SELECT variant, COUNT(*) AS n_users
        FROM users
        WHERE experiment_id = ?
        GROUP BY 1
        """,
        [args.experiment_id],
    ).fetchdf()

    sessions = con.execute(
        """
        SELECT variant, COUNT(*) AS n_sessions
        FROM fact_sessions
        WHERE experiment_id = ?
          AND is_experiment_period = TRUE
        GROUP BY 1
        """,
        [args.experiment_id],
    ).fetchdf()

    u_c = _get_count(users, "n_users", "control")
    u_t = _get_count(users, "n_users", "treatment")
    s_c = _get_count(sessions, "n_sessions", "control")
    s_t = _get_count(sessions, "n_sessions", "treatment")

    chi_u, p_u = _srm_pval(u_c, u_t, args.expected_treatment_share)
    chi_s, p_s = _srm_pval(s_c, s_t, args.expected_treatment_share)

    # ---------- Guardrails (experiment period only) ----------
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
        [args.experiment_id],
    ).fetchdf()

    # ---------- Daily trend data (if available) ----------
    cols = con.execute("PRAGMA table_info('daily_metrics')").fetchdf()["name"].tolist()
    has_period_col = "is_experiment_period" in cols

    if has_period_col:
        daily = con.execute(
            """
            SELECT
              event_date, variant, is_experiment_period,
              sessions, purchase_rate_per_session, revenue_per_session, ctr, atc_rate
            FROM daily_metrics
            WHERE experiment_id = ?
            ORDER BY event_date, variant
            """,
            [args.experiment_id],
        ).fetchdf()
    else:
        # fallback: still pull trends without explicit flag
        daily = con.execute(
            """
            SELECT
              event_date, variant,
              sessions, purchase_rate_per_session, revenue_per_session, ctr, atc_rate
            FROM daily_metrics
            WHERE experiment_id = ?
            ORDER BY event_date, variant
            """,
            [args.experiment_id],
        ).fetchdf()

    con.close()

    # ---------- A/B Readout (formatted table) ----------
    readout = run_readout(args.db, args.experiment_id)

    # Decision rule (same as dashboard)
    primary = readout[readout["metric"] == "purchase_rate_per_session"].iloc[0]
    pval_primary = float(primary["p_value"])
    abs_diff_num = float(str(primary["abs_diff"]).replace("%", "")) / 100.0
    ship = (pval_primary < 0.05) and (abs_diff_num > 0)

    # Trend summary (simple)
    trend_notes = ""
    if daily is not None and not daily.empty:
        daily["event_date"] = pd.to_datetime(daily["event_date"])
        last7 = daily[daily["event_date"] >= (daily["event_date"].max() - pd.Timedelta(days=6))].copy()
        if not last7.empty:
            piv = last7.pivot_table(
                index="event_date", columns="variant", values="purchase_rate_per_session", aggfunc="mean"
            )
            if "control" in piv.columns and "treatment" in piv.columns:
                avg_c = float(piv["control"].mean())
                avg_t = float(piv["treatment"].mean())
                trend_notes = (
                    f"- Last 7 days avg purchase/session: control={avg_c:.4%}, "
                    f"treatment={avg_t:.4%} (Δ={avg_t-avg_c:.4%})"
                )
            else:
                trend_notes = "- Trend summary: insufficient variant coverage in last 7 days."

    daily_preview = ("\n" + _table_md(daily.head(14))) if (daily is not None and not daily.empty) else ""

    # ---------- Build Markdown ----------
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_md = f"""# LaunchLens Experiment Report

**Experiment:** `{args.experiment_id}`  
**Generated:** {now}  
**Data source:** `{args.db}`  

---

## Decision Summary

**Recommendation:** {"✅ Ship" if ship else "⚠️ Hold / Continue Experiment"}  
**Primary metric:** `purchase_rate_per_session`  
- Δ (T-C): {primary["abs_diff"]}  
- 95% CI: [{primary["ci_low"]}, {primary["ci_high"]}]  
- p-value: {primary["p_value"]}

---

## Sample Ratio Mismatch (SRM)

**User-level (primary SRM check):**  
- control={u_c:,}, treatment={u_t:,}  
- chi2={chi_u:.3f}, p={p_u:.4f} → {"OK ✅" if p_u >= 0.01 else "SRM ❌"}

**Session-level (diagnostic):**  
- control={s_c:,}, treatment={s_t:,}  
- chi2={chi_s:.3f}, p={p_s:.4f} → {"OK ✅" if p_s >= 0.01 else "Flag ⚠️"}

> Note: Session-level imbalance can happen even with correct user randomization due to activity differences.

---

## A/B Readout (Experiment Period)

{_table_md(readout)}

---

## Guardrails (Experiment Period)

{_table_md(guard)}

---

## Trends (Daily)

{trend_notes if trend_notes else "- Trend summary not available."}
{daily_preview}
"""

    out_path = out_dir / f"{args.experiment_id}_report.md"
    out_path.write_text(report_md, encoding="utf-8")

    print(f"✅ Report written: {out_path}")


if __name__ == "__main__":
    main()
