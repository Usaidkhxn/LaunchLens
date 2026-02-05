# LaunchLens Metric Dictionary

## Primary metric
### purchase_rate_per_session
**Definition:** Sessions with a purchase / total sessions (experiment period)  
**Unit:** proportion  
**Why it matters:** Measures end-to-end conversion lift attributable to the launch.

---

## Guardrails
### ctr
**Definition:** Sessions with click / sessions with impression  
**Why:** Detects top-of-funnel changes that may indicate logging issues or UX regressions.

### atc_rate
**Definition:** Sessions with add_to_cart / sessions with click  
**Why:** Measures mid-funnel intent.

### purchase_rate_given_atc
**Definition:** Sessions with purchase / sessions with add_to_cart  
**Why:** Captures checkout effectiveness (this is where treatment lift is injected in the simulator).

### revenue_per_session
**Definition:** Total revenue / total sessions  
**Why:** Business impact metric; can be noisy and benefits from variance reduction (CUPED).
