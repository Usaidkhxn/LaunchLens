"""
LaunchLens - Experiment Monitoring: SRM + Guardrails

SRM (Sample Ratio Mismatch):
- Checks if observed assignment proportions differ from expected split
- Uses chi-square test

Guardrails:
- CTR, ATC rate, Purchase rate/session, Revenue/session
- Session counts by variant and experiment period
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class SRMResult:
    level: str
    n_control: int
    n_treatment: int
    expected_share_treatment: float
    chi2: float
    p_value: float


def srm_test(n_control: int, n_treatment: int, expected_share_treatment: float) -> SRMResult:
    total = n_control + n_treatment
    exp_t = total * expected_share_treatment
    exp_c = total * (1.0 - expected_share_treatment)

    observed = np.array([n_control, n_treatment], dtype=float)
    expected = np.array([exp_c, exp_t], dtype=float)

    chi2, p = stats.chisquare(f_obs=observed, f_exp=expected)
    return SRMResult(
        level="count",
        n_control=int(n_control),
        n_treatment=int(n_treatment),
        expected_share_treatment=float(expected_share_treatment),
        chi2=float(chi2),
        p_value=float(p),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=str, default="data/launchlens.duckdb")
    ap.add_argument("--experiment_id", type=str, default="exp_checkout_v1")
    ap.add_argument("--expected_treatment_share", type=float, default=0.50)
    args = ap.parse_args()

    con = duckdb.connect(args.db)

    # SRM at USER level (recommended)
    users = con.execute(
        """
        SELECT variant, COUNT(*) AS n_users
        FROM users
        WHERE experiment_id = ?
        GROUP BY 1
        """,
        [args.experiment_id],
    ).fetchdf()

    # SRM at SESSION level (also useful)
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

    # Guardrail rollup (experiment period only)
    guard = con.execute(
        """
        SELECT
          variant,
          COUNT(*) AS sessions,
          AVG(has_impression)::DOUBLE AS impression_rate,
          AVG(has_click)::DOUBLE AS click_rate,
          AVG(has_add_to_cart)::DOUBLE AS atc_rate_per_session,
          AVG(has_purchase)::DOUBLE AS purchase_rate_per_session,
          AVG(revenue)::DOUBLE AS revenue_per_session,
          -- CTR among impression sessions
          (SUM(has_click)::DOUBLE / NULLIF(SUM(has_impression), 0)) AS ctr,
          -- ATC rate among click sessions
          (SUM(has_add_to_cart)::DOUBLE / NULLIF(SUM(has_click), 0)) AS atc_rate_given_click
        FROM fact_sessions
        WHERE experiment_id = ?
          AND is_experiment_period = TRUE
        GROUP BY 1
        ORDER BY 1
        """,
        [args.experiment_id],
    ).fetchdf()

    con.close()

    # SRM calc helpers
    def get_count(df: pd.DataFrame, col: str, label: str) -> int:
        sub = df[df["variant"] == label]
        if sub.empty:
            return 0
        return int(sub[col].iloc[0])

    u_c = get_count(users, "n_users", "control")
    u_t = get_count(users, "n_users", "treatment")
    s_c = get_count(sessions, "n_sessions", "control")
    s_t = get_count(sessions, "n_sessions", "treatment")

    user_srm = srm_test(u_c, u_t, args.expected_treatment_share)
    sess_srm = srm_test(s_c, s_t, args.expected_treatment_share)

    print("\n✅ LaunchLens Monitoring: SRM + Guardrails (experiment period)\n")

    print("SRM (User-level assignment)")
    print(f"  control={user_srm.n_control:,}  treatment={user_srm.n_treatment:,}  expected_treat={user_srm.expected_share_treatment:.2f}")
    print(f"  chi2={user_srm.chi2:.3f}  p={user_srm.p_value:.4f}")
    print("  FLAG:" + (" ✅ OK (no SRM)" if user_srm.p_value >= 0.01 else " ❌ SRM detected (p<0.01)"))

    print("\nSRM (Session-level, experiment period)")
    print(f"  control={sess_srm.n_control:,}  treatment={sess_srm.n_treatment:,}  expected_treat={sess_srm.expected_share_treatment:.2f}")
    print(f"  chi2={sess_srm.chi2:.3f}  p={sess_srm.p_value:.4f}")
    print("  FLAG:" + (" ✅ OK (no SRM)" if sess_srm.p_value >= 0.01 else " ❌ SRM detected (p<0.01)"))

    print("\nGuardrail metrics (experiment period)")
    pd.set_option("display.max_columns", None)
    print(guard.to_string(index=False))


if __name__ == "__main__":
    main()
