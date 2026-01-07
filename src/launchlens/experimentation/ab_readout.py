"""
LaunchLens - A/B test readout (DuckDB + stats)

Outputs a decision-ready table for experiment period:
- purchase_rate_per_session (primary)
- revenue_per_session
- ctr
- atc_rate
- purchase_rate_given_atc

Uses session-level data to compute:
- Control mean, Treatment mean
- Absolute diff, Relative diff
- 95% CI and p-value (two-sided)
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Dict, Tuple

import duckdb
import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class MetricResult:
    metric: str
    control: float
    treatment: float
    abs_diff: float
    rel_diff: float
    ci_low: float
    ci_high: float
    p_value: float


def _two_proportion_ztest(x1: int, n1: int, x2: int, n2: int) -> Tuple[float, float, float, float]:
    """
    Returns: (p1, p2, diff, (ci_low, ci_high), p_value) but CI returned separately in main.
    """
    if n1 == 0 or n2 == 0:
        return 0.0, 0.0, 0.0, (0.0, 0.0), 1.0

    p1 = x1 / n1
    p2 = x2 / n2
    diff = p2 - p1

    # Standard error for difference in proportions (unpooled for CI)
    se_ci = math.sqrt((p1 * (1 - p1) / n1) + (p2 * (1 - p2) / n2))
    z = stats.norm.ppf(0.975)
    ci_low, ci_high = diff - z * se_ci, diff + z * se_ci

    # P-value using pooled SE for z-test
    p_pool = (x1 + x2) / (n1 + n2)
    se_pooled = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se_pooled == 0:
        p_value = 1.0
    else:
        z_stat = diff / se_pooled
        p_value = 2 * (1 - stats.norm.cdf(abs(z_stat)))

    return p1, p2, diff, (ci_low, ci_high), p_value


def _two_sample_ttest(a: np.ndarray, b: np.ndarray) -> Tuple[float, float, float]:
    """
    Welch's t-test + CI for mean difference (b - a).
    Returns (diff, (ci_low, ci_high), p_value)
    """
    a = a.astype(float)
    b = b.astype(float)
    if len(a) < 2 or len(b) < 2:
        return 0.0, (0.0, 0.0), 1.0

    diff = float(np.mean(b) - np.mean(a))
    tstat, p_value = stats.ttest_ind(b, a, equal_var=False, nan_policy="omit")

    # Welch-Satterthwaite df
    va = np.var(a, ddof=1)
    vb = np.var(b, ddof=1)
    na, nb = len(a), len(b)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return diff, (diff, diff), 1.0

    df_num = (va / na + vb / nb) ** 2
    df_den = (va**2) / (na**2 * (na - 1)) + (vb**2) / (nb**2 * (nb - 1))
    df = df_num / df_den if df_den > 0 else (na + nb - 2)

    tcrit = stats.t.ppf(0.975, df)
    ci_low, ci_high = diff - tcrit * se, diff + tcrit * se
    return diff, (ci_low, ci_high), float(p_value)


def run_readout(db_path: str, experiment_id: str) -> pd.DataFrame:
    con = duckdb.connect(db_path)

    # session-level experiment-period data
    df = con.execute(
        """
        SELECT
          variant,
          has_impression,
          has_click,
          has_add_to_cart,
          has_purchase,
          revenue
        FROM fact_sessions
        WHERE experiment_id = ?
          AND is_experiment_period = TRUE
        """,
        [experiment_id],
    ).fetchdf()
    con.close()

    if df.empty:
        raise ValueError("No experiment-period sessions found. Check experiment_id or data.")

    out: Dict[str, MetricResult] = {}

    # Split
    c = df[df["variant"] == "control"]
    t = df[df["variant"] == "treatment"]

    n_c = len(c)
    n_t = len(t)

    # 1) purchase_rate_per_session (proportion)
    x_c = int(c["has_purchase"].sum())
    x_t = int(t["has_purchase"].sum())
    p1, p2, diff, (ci_low, ci_high), pval = _two_proportion_ztest(x_c, n_c, x_t, n_t)
    out["purchase_rate_per_session"] = MetricResult(
        metric="purchase_rate_per_session",
        control=p1,
        treatment=p2,
        abs_diff=diff,
        rel_diff=(diff / p1) if p1 > 0 else np.nan,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=pval,
    )

    # 2) ctr = click/impression (use impression sessions as denom)
    imp_c = int(c["has_impression"].sum())
    imp_t = int(t["has_impression"].sum())
    clk_c = int(c["has_click"].sum())
    clk_t = int(t["has_click"].sum())
    p1, p2, diff, (ci_low, ci_high), pval = _two_proportion_ztest(clk_c, imp_c, clk_t, imp_t)
    out["ctr"] = MetricResult(
        metric="ctr",
        control=p1,
        treatment=p2,
        abs_diff=diff,
        rel_diff=(diff / p1) if p1 > 0 else np.nan,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=pval,
    )

    # 3) atc_rate = add_to_cart / click (click sessions denom)
    atc_c = int(c["has_add_to_cart"].sum())
    atc_t = int(t["has_add_to_cart"].sum())
    p1, p2, diff, (ci_low, ci_high), pval = _two_proportion_ztest(atc_c, clk_c, atc_t, clk_t)
    out["atc_rate"] = MetricResult(
        metric="atc_rate",
        control=p1,
        treatment=p2,
        abs_diff=diff,
        rel_diff=(diff / p1) if p1 > 0 else np.nan,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=pval,
    )

    # 4) purchase_rate_given_atc = purchase / atc (atc denom)
    p1, p2, diff, (ci_low, ci_high), pval = _two_proportion_ztest(x_c, atc_c, x_t, atc_t)
    out["purchase_rate_given_atc"] = MetricResult(
        metric="purchase_rate_given_atc",
        control=p1,
        treatment=p2,
        abs_diff=diff,
        rel_diff=(diff / p1) if p1 > 0 else np.nan,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=pval,
    )

    # 5) revenue_per_session (continuous)
    diff, (ci_low, ci_high), pval = _two_sample_ttest(c["revenue"].to_numpy(), t["revenue"].to_numpy())
    out["revenue_per_session"] = MetricResult(
        metric="revenue_per_session",
        control=float(np.mean(c["revenue"])),
        treatment=float(np.mean(t["revenue"])),
        abs_diff=diff,
        rel_diff=(diff / float(np.mean(c["revenue"]))) if float(np.mean(c["revenue"])) > 0 else np.nan,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=pval,
    )

    res = pd.DataFrame([vars(v) for v in out.values()])

    # formatting helpers
    def fmt_pct(x):
        return f"{x*100:.3f}%" if pd.notnull(x) else "NA"

    def fmt_num(x):
        return f"{x:.4f}" if pd.notnull(x) else "NA"

    def fmt_money(x):
        return f"{x:.4f}" if pd.notnull(x) else "NA"

    # Presentable table
        # ---------- Build formatted output table (strings only) ----------
    out_rows = []
    for _, r in res.iterrows():
        m = r["metric"]

        def pct(x): return f"{float(x)*100:.3f}%"
        def rel(x): return f"{float(x)*100:.2f}%"
        def num(x): return f"{float(x):.4f}"

        row = {"metric": m}

        if m in {"purchase_rate_per_session", "ctr", "atc_rate", "purchase_rate_given_atc"}:
            row["control"] = pct(r["control"])
            row["treatment"] = pct(r["treatment"])
            row["abs_diff"] = pct(r["abs_diff"])
            row["rel_diff"] = rel(r["rel_diff"]) if pd.notnull(r["rel_diff"]) else "NA"
            row["ci_low"] = pct(r["ci_low"])
            row["ci_high"] = pct(r["ci_high"])
            row["p_value"] = num(r["p_value"])
        else:  # revenue_per_session
            row["control"] = num(r["control"])
            row["treatment"] = num(r["treatment"])
            row["abs_diff"] = num(r["abs_diff"])
            row["rel_diff"] = rel(r["rel_diff"]) if pd.notnull(r["rel_diff"]) else "NA"
            row["ci_low"] = num(r["ci_low"])
            row["ci_high"] = num(r["ci_high"])
            row["p_value"] = num(r["p_value"])

        out_rows.append(row)

    display = pd.DataFrame(out_rows)
    display = display[["metric", "control", "treatment", "abs_diff", "rel_diff", "ci_low", "ci_high", "p_value"]]
    return display.sort_values("metric").reset_index(drop=True)



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=str, default="data/launchlens.duckdb")
    ap.add_argument("--experiment_id", type=str, default="exp_checkout_v1")
    args = ap.parse_args()

    table = run_readout(args.db, args.experiment_id)
    print("\n✅ LaunchLens A/B Readout (experiment period only)")
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
