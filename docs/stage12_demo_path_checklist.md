# Stage 12 reproducible demo path

Status: **PASS**. The path below was executed against the real Streamlit entry point with no exceptions, missing data, mock fallback, or manual backend intervention.

## Launch

From the repository root, with the Stage 11 requirements installed:

```powershell
python -m streamlit run app/app.py --global.developmentMode false --server.headless true --server.port 8513 --browser.gatherUsageStats false
```

The Stage 12 runtime harness used the equivalent explicit interpreter command recorded in `artifacts/stage12/stage12_runtime_validation.json`. HTTP `/` and `/_stcore/health` both returned 200; the health body was `ok`.

## Recommended Stage 13 preparation sequence

1. **Overview** — establish the 61-day synthetic Scenario 3 household and the product-wide current-versus-optimized headline. Point out that annual values are `ANNUALIZED ESTIMATE` and payback is `SIMPLE PAYBACK`.
2. **Historical Consumption** — show the 1,464-hour Aug–Sep digital twin, total 2,834.740 kWh, maximum hour 21.699 kWh, occupancy/AWAY context, weather, and component breakdown.
3. **Forecast** — select 24 h, then 72 h, then 168 h. Distinguish `EXPECTED DEMAND` from uncertainty bands and `PEAK RISK / HIGH-DEMAND POTENTIAL`; do not describe the point forecast as an exact stochastic-spike prediction.
4. **Peak Hours** — show the frozen Stage 6B risk ranking, LOW/MEDIUM/HIGH probability mapping, P95 high-demand potential, and the directly sourced primary/secondary explanations for the displayed hour.
5. **Tariff** — confirm €0.18 at 00:00–06:00, €0.28 at 06:00–17:00, €0.40 at 17:00–22:00, and €0.28 at 22:00–00:00.
6. **Flexibility (Stage 7)** — show A fixed, B behavioral/not optimized, C limited flexibility, and D shiftable. Use production events—not static UI examples—to demonstrate energy, duration, power, windows, deadlines, dependencies, EV availability, AWAY compatibility, and boundary accounting.
7. **Optimizer** — use 2025-08-03 as the reproducible example day, then show the full-period current/optimized totals and shifted-event ledger. State that modeled flexible services are preserved and that zero avoidable occupied comfort violation is introduced; do not claim universal real-world comfort.
8. **PV Simulator** — retain the default 5 kWp comparison. Show current versus optimized PV use, grid purchase, annualized net cost, and simple payback. Separate the €1,162.52/year no-PV behavioral benefit from PV and combined benefits.

This sequence proves the intended story:

`HISTORICAL HOUSEHOLD → EXPECTED DEMAND → PEAK RISK → WHY → FLEXIBILITY → OPTIMIZED SCHEDULE → COST / GRID / PEAK IMPACT → PV CURRENT VS OPTIMIZED → ECONOMICS`

All eight page executions and all eight demo steps are machine-recorded as PASS in the runtime artifact.
