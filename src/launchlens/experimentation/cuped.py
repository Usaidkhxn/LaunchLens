"""
LaunchLens - CUPED variance reduction for experiment metrics

CUPED adjusts a metric Y using a pre-period covariate X:
Y* = Y - theta * (X - mean(X))

We use:
- Y: revenue_per_user_during_experiment (sum of revenue across sessions)
- X: pre_rev from users table (already generated)

Outputs:
- Control mean (raw vs cuped)
- Treatment mean (raw vs cuped)
- Diff + CI + p-value (raw vs cuped)
- Variance reduction %
"""

from __future__ import annotations

import argparse
import math

import duckdb
import numpy as np
import pandas as pd
from scipy import stats


def welch_ttest_ci(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float, float]:
    """Return (diff, ci_low, ci_high, p_value) for diff = mean(b)-mean(a)."""
    a = a.astype(float)
    b = b.astype(float)

    diff = float(np.mean(b) - np.mean(a))

    va = np.var(a, ddof=1)
    vb = np.var(b, ddof=1)
    na, nb = len(a), len(b)
    se = math.sqrt(va / na + vb / nb)

    if se == 0 or na < 2 or nb < 2:
        return diff, diff, diff, 1.0

    # Welch df
    df_num = (va / na + vb / nb) ** 2
    df_den = (va**2) / (na**2 * (na - 1)) + (vb**2) / (nb**2 * (nb - 1))
    df = df_num / df_den if df_den > 0 else (na + nb - 2)

    tcrit = stats.t.ppf(0.975, df)
    ci_low, ci_high = diff - tcrit * se, diff + tcrit * se

    tstat, p_value = stats.ttest_ind(b, a, equal_var=False, nan_policy="omit")
    return diff, float(ci_low), float(ci_high), float(p_value)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=str, default="data/launchlens.duckdb")
    ap.add_argument("--experiment_id", type=str, default="exp_checkout_v1")
    args = ap.parse_args()

    con = duckdb.connect(args.db)

    # Build user-level dataset:
    # Y = total revenue during experiment period
    # X = pre_rev (pre-period covariate)
    df = con.execute(
        """
        WITH y AS (
          SELECT
            user_id,
            ANY_VALUE(variant) AS variant,
            SUM(revenue) AS y_rev
          FROM fact_sessions
          WHERE experiment_id = ?
            AND is_experiment_period = TRUE
          GROUP BY user_id
        )
        SELECT
          y.user_id,
          y.variant,
          COALESCE(y.y_rev, 0.0) AS y_rev,
          u.pre_rev AS x_pre_rev
        FROM y
        JOIN users u USING (user_id)
        """,
        [args.experiment_id],
    ).fetchdf()
    con.close()

    # CUPED theta = cov(Y, X)/var(X)
    x = df["x_pre_rev"].to_numpy(dtype=float)
    y = df["y_rev"].to_numpy(dtype=float)

    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))

    cov_yx = float(np.cov(y, x, ddof=1)[0, 1])
    var_x = float(np.var(x, ddof=1))
    theta = cov_yx / var_x if var_x > 0 else 0.0

    y_cuped = y - theta * (x - x_mean)
    df["y_rev_cuped"] = y_cuped

    # Split
    c = df[df["variant"] == "control"]
    t = df[df["variant"] == "treatment"]

    raw_c = c["y_rev"].to_numpy()
    raw_t = t["y_rev"].to_numpy()
    cup_c = c["y_rev_cuped"].to_numpy()
    cup_t = t["y_rev_cuped"].to_numpy()

    # Raw stats
    raw_diff, raw_lo, raw_hi, raw_p = welch_ttest_ci(raw_c, raw_t)

    # CUPED stats
    cup_diff, cup_lo, cup_hi, cup_p = welch_ttest_ci(cup_c, cup_t)

    # Variance reduction (on overall variance of metric)
    var_raw = float(np.var(y, ddof=1))
    var_cup = float(np.var(y_cuped, ddof=1))
    var_red = (1 - (var_cup / var_raw)) if var_raw > 0 else 0.0

    # Print report
    def f(x): return f"{x:.4f}"

    print("\n✅ LaunchLens CUPED Readout (user-level revenue during experiment)")
    print(f"- theta (CUPED): {theta:.6f}")
    print(f"- Variance reduction: {var_red*100:.2f}%\n")

    print("RAW revenue_per_user (experiment period)")
    print(f"  control mean:   {f(np.mean(raw_c))}")
    print(f"  treatment mean: {f(np.mean(raw_t))}")
    print(f"  diff (T-C):     {f(raw_diff)}   95% CI [{f(raw_lo)}, {f(raw_hi)}]   p={f(raw_p)}\n")

    print("CUPED-adjusted revenue_per_user")
    print(f"  control mean:   {f(np.mean(cup_c))}")
    print(f"  treatment mean: {f(np.mean(cup_t))}")
    print(f"  diff (T-C):     {f(cup_diff)}   95% CI [{f(cup_lo)}, {f(cup_hi)}]   p={f(cup_p)}")


if __name__ == "__main__":
    main()
