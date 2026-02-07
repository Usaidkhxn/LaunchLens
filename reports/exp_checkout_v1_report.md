# LaunchLens Experiment Report

**Experiment:** `exp_checkout_v1`  
**Generated:** 2026-01-07 17:25:59  
**Data source:** `data/launchlens.duckdb`  

---

## Decision Summary

**Recommendation:** Hold / Continue Experiment  
**Primary metric:** `purchase_rate_per_session`  
- Δ (T-C): 0.132%  
- 95% CI: [-0.028%, 0.292%]  
- p-value: 0.1046

---

## Sample Ratio Mismatch (SRM)

**User-level (primary SRM check):**  
- control=4,031, treatment=3,969  
- chi2=0.480, p=0.4882 → OK 

**Session-level (diagnostic):**  
- control=21,238, treatment=20,706  
- chi2=6.748, p=0.0094 → Flag 

> Note: Session-level imbalance can happen even with correct user randomization due to activity differences.

---

## A/B Readout (Experiment Period)

| metric                    | control   | treatment   | abs_diff   | rel_diff   | ci_low   | ci_high   |   p_value |
|:--------------------------|:----------|:------------|:-----------|:-----------|:---------|:----------|----------:|
| atc_rate                  | 23.607%   | 22.535%     | -1.071%    | -4.54%     | -3.459%  | 1.316%    |    0.3794 |
| ctr                       | 11.489%   | 11.316%     | -0.173%    | -1.51%     | -0.782%  | 0.435%    |    0.5767 |
| purchase_rate_given_atc   | 23.438%   | 30.114%     | 6.676%     | 28.48%     | 1.453%   | 11.899%   |    0.0122 |
| purchase_rate_per_session | 0.636%    | 0.768%      | 0.132%     | 20.80%     | -0.028%  | 0.292%    |    0.1046 |
| revenue_per_session       | 0.2283    | 0.2789      | 0.0506     | 22.16%     | -0.0165  | 0.1177    |    0.1396 |

---

## Guardrails (Experiment Period)

| variant   |   sessions |   click_rate |   atc_rate_per_session |   purchase_rate_per_session |   revenue_per_session |      ctr |   atc_rate_given_click |
|:----------|-----------:|-------------:|-----------------------:|----------------------------:|----------------------:|---------:|-----------------------:|
| control   |      21238 |     0.114888 |              0.0271212 |                  0.00635653 |              0.228266 | 0.114888 |               0.236066 |
| treatment |      20706 |     0.113156 |              0.0254999 |                  0.00767893 |              0.278859 | 0.113156 |               0.225352 |

---

## Trends (Daily)

- Last 7 days avg purchase/session: control=0.6784%, treatment=0.7909% (Δ=0.1125%)

| event_date          | variant   |   is_experiment_period |   sessions |   purchase_rate_per_session |   revenue_per_session |      ctr |   atc_rate |
|:--------------------|:----------|-----------------------:|-----------:|----------------------------:|----------------------:|---------:|-----------:|
| 2025-01-01 00:00:00 | control   |                      0 |       1551 |                  0.00773694 |              0.282433 | 0.112186 |   0.201149 |
| 2025-01-01 00:00:00 | treatment |                      0 |       1442 |                  0.00346741 |              0.169303 | 0.131068 |   0.21164  |
| 2025-01-02 00:00:00 | control   |                      0 |       1461 |                  0.00752909 |              0.262238 | 0.119781 |   0.217143 |
| 2025-01-02 00:00:00 | treatment |                      0 |       1506 |                  0.0059761  |              0.180127 | 0.11089  |   0.263473 |
| 2025-01-03 00:00:00 | control   |                      0 |       1553 |                  0.00450741 |              0.232169 | 0.110109 |   0.204678 |
| 2025-01-03 00:00:00 | treatment |                      0 |       1461 |                  0.0109514  |              0.294526 | 0.114305 |   0.233533 |
| 2025-01-04 00:00:00 | control   |                      0 |       1497 |                  0.00868403 |              0.313827 | 0.118236 |   0.220339 |
| 2025-01-04 00:00:00 | treatment |                      0 |       1497 |                  0.00668003 |              0.191358 | 0.1169   |   0.2      |
| 2025-01-05 00:00:00 | control   |                      0 |       1543 |                  0.00842515 |              0.230146 | 0.132858 |   0.253659 |
| 2025-01-05 00:00:00 | treatment |                      0 |       1476 |                  0.00474255 |              0.178231 | 0.112466 |   0.228916 |
| 2025-01-06 00:00:00 | control   |                      0 |       1395 |                  0.00573477 |              0.210006 | 0.107527 |   0.186667 |
| 2025-01-06 00:00:00 | treatment |                      0 |       1429 |                  0.0069979  |              0.212448 | 0.128761 |   0.179348 |
| 2025-01-07 00:00:00 | control   |                      0 |       1550 |                  0.0122581  |              0.526729 | 0.11871  |   0.266304 |
| 2025-01-07 00:00:00 | treatment |                      0 |       1467 |                  0.00477164 |              0.2185   | 0.102249 |   0.24     |
