"""
LaunchLens - Warehouse builder (DuckDB)

Inputs:
- data/launchlens.duckdb with tables: users, events

Creates:
- fact_sessions: session-level fact table (one row per user-session)
- fact_sessions_daily: session-level with derived event_date
- daily_metrics: variant/day rollups (funnel + revenue)
- dq_checks: basic data quality checks + pass/fail flags
"""

from __future__ import annotations

import argparse
import duckdb


WAREHOUSE_SQL = r"""
-- Ensure base tables exist
CREATE OR REPLACE VIEW v_events AS
SELECT
  CAST(event_time AS TIMESTAMP) AS event_time,
  CAST(event_time AS DATE) AS event_date,
  user_id::BIGINT AS user_id,
  session_id::VARCHAR AS session_id,
  event_type::VARCHAR AS event_type,
  item_id::BIGINT AS item_id,
  experiment_id::VARCHAR AS experiment_id,
  variant::VARCHAR AS variant,
  is_experiment_period::BOOLEAN AS is_experiment_period,
  revenue::DOUBLE AS revenue
FROM events;

-- Session-level funnel flags
CREATE OR REPLACE TABLE fact_sessions AS
WITH sess AS (
  SELECT
    user_id,
    session_id,
    MIN(event_time) AS session_start_time,
    MIN(event_date) AS event_date,
    ANY_VALUE(experiment_id) AS experiment_id,
    ANY_VALUE(variant) AS variant,
    BOOL_OR(is_experiment_period) AS is_experiment_period,
    MAX(CASE WHEN event_type = 'impression' THEN 1 ELSE 0 END) AS has_impression,
    MAX(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) AS has_click,
    MAX(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END) AS has_add_to_cart,
    MAX(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS has_purchase,
    SUM(CASE WHEN event_type = 'purchase' THEN revenue ELSE 0 END) AS revenue
  FROM v_events
  GROUP BY user_id, session_id
)
SELECT * FROM sess;

-- Daily rollups per variant
CREATE OR REPLACE TABLE daily_metrics AS
SELECT
  event_date,
  experiment_id,
  variant,
  MAX(CASE WHEN is_experiment_period THEN 1 ELSE 0 END) AS is_experiment_period,
  COUNT(*) AS sessions,
  SUM(has_impression) AS sessions_with_impression,
  SUM(has_click) AS sessions_with_click,
  SUM(has_add_to_cart) AS sessions_with_add_to_cart,
  SUM(has_purchase) AS sessions_with_purchase,
  SUM(revenue) AS revenue,
  -- Key rates (avoid div0)
  CASE WHEN SUM(has_impression) = 0 THEN 0
       ELSE SUM(has_click)::DOUBLE / SUM(has_impression) END AS ctr,
  CASE WHEN SUM(has_click) = 0 THEN 0
       ELSE SUM(has_add_to_cart)::DOUBLE / SUM(has_click) END AS atc_rate,
  CASE WHEN SUM(has_add_to_cart) = 0 THEN 0
       ELSE SUM(has_purchase)::DOUBLE / SUM(has_add_to_cart) END AS purchase_rate_given_atc,
  CASE WHEN COUNT(*) = 0 THEN 0
       ELSE SUM(has_purchase)::DOUBLE / COUNT(*) END AS purchase_rate_per_session,
  CASE WHEN COUNT(*) = 0 THEN 0
       ELSE SUM(revenue)::DOUBLE / COUNT(*) END AS revenue_per_session
FROM fact_sessions
GROUP BY event_date, experiment_id, variant
ORDER BY event_date, variant;

-- Data quality checks
CREATE OR REPLACE TABLE dq_checks AS
WITH checks AS (
  SELECT 'events_nonempty' AS check_name,
         (SELECT COUNT(*) FROM events) AS observed,
         1 AS threshold_min,
         CASE WHEN (SELECT COUNT(*) FROM events) >= 1 THEN TRUE ELSE FALSE END AS pass
  UNION ALL
  SELECT 'users_nonempty',
         (SELECT COUNT(*) FROM users),
         1,
         CASE WHEN (SELECT COUNT(*) FROM users) >= 1 THEN TRUE ELSE FALSE END
  UNION ALL
  SELECT 'no_null_user_ids_events',
         (SELECT COUNT(*) FROM events WHERE user_id IS NULL),
         0,
         CASE WHEN (SELECT COUNT(*) FROM events WHERE user_id IS NULL) = 0 THEN TRUE ELSE FALSE END
  UNION ALL
  SELECT 'no_null_session_ids_events',
         (SELECT COUNT(*) FROM events WHERE session_id IS NULL),
         0,
         CASE WHEN (SELECT COUNT(*) FROM events WHERE session_id IS NULL) = 0 THEN TRUE ELSE FALSE END
  UNION ALL
  SELECT 'valid_event_types',
         (SELECT COUNT(*) FROM events WHERE event_type NOT IN ('impression','click','add_to_cart','purchase')),
         0,
         CASE WHEN (SELECT COUNT(*) FROM events WHERE event_type NOT IN ('impression','click','add_to_cart','purchase')) = 0 THEN TRUE ELSE FALSE END
)
SELECT * FROM checks;
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=str, default="data/launchlens.duckdb")
    args = ap.parse_args()

    con = duckdb.connect(args.db)
    con.execute(WAREHOUSE_SQL)

    # Print summaries
    dm = con.execute(
        "SELECT variant, SUM(sessions) AS sessions, SUM(sessions_with_purchase) AS purchases, SUM(revenue) AS revenue "
        "FROM daily_metrics GROUP BY 1 ORDER BY 1"
    ).fetchdf()

    dq = con.execute("SELECT * FROM dq_checks ORDER BY check_name").fetchdf()
    con.close()

    print("✅ Warehouse built: fact_sessions, daily_metrics, dq_checks")
    print("\nDaily totals by variant:")
    print(dm.to_string(index=False))
    print("\nDQ checks:")
    print(dq.to_string(index=False))

    if not dq["pass"].all():
        raise SystemExit("❌ Data quality checks failed. Fix before proceeding.")


if __name__ == "__main__":
    main()
