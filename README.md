# LaunchLens 
**Decision-ready experiment monitoring for product launches** - from raw event telemetry to A/B readouts, guardrails, SRM checks, daily trends, and an auto-generated experiment report.

This project is built to mirror **real Product Data Scientist workflows**: metrics definition, experimentation, monitoring, and decision-making under uncertainty.

![LaunchLens Dashboard](assets/dasboard-1.png)
---



## What LaunchLens does
- **Generates product telemetry** (session-based funnel events) with a known ground-truth treatment lift  
- Builds a simple **warehouse in DuckDB**:
  - `fact_sessions` (one row per user-session with funnel flags + revenue)
  - `daily_metrics` (variant/day rollups)
  - `dq_checks` (data-quality checks)
- Produces a **decision-ready A/B readout**:
  - lift, 95% CI, p-values
  - primary metric + guardrails
- Runs **SRM (sample ratio mismatch)** checks:
  - user-level (primary)
  - session-level (diagnostic)
- Shows **daily trend charts** in Streamlit
- Generates a **Markdown experiment report** and supports **download from the dashboard**

---

## Example Experiment Report (Decision Output)

LaunchLens automatically generates a **decision-ready Markdown report** for each experiment run.

These reports are designed to be:
- shared directly with stakeholders
- pasted into launch decision docs
- archived for experiment history

📄 **Example output:**  
[`exp_checkout_v1_report.md`](reports/exp_checkout_v1_report.md)

### What the report contains
- **Decision summary** (ship / hold / continue)
- **Primary metric** with lift, 95% CI, and p-value
- **SRM checks** (user-level and session-level)
- **Guardrail metrics**
- **Daily trends** for stability analysis

The report is generated automatically from DuckDB after the experiment completes - no manual analysis required.


---

## Demo Screens

![Daily Trends](assets/dasboard-2.png)


---

## Quickstart (Windows, 5 minutes)
### One-command demo
```powershell
.\demo.ps1
```

See metric definitions in **METRICS.md**.



