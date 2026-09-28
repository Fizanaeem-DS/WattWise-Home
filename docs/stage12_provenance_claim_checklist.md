# Stage 12 provenance and claim checklist

Status: **PASS** for every final page and major product claim.

| Product evidence | Authoritative source | Allowed claim | Prohibited implication |
|---|---|---|---|
| Historical household | Frozen Stage 3C hourly realization | Scenario-specific synthetic digital twin; 1,464 hours; 2,834.740433147 kWh | Measured Anna/Robert smart-meter data |
| Occupancy/AWAY and components | Frozen Stage 3 event/hourly artifacts | Exact scenario states and reconciled component totals | Inferred from a live home |
| Weather | Frozen Barcelona weather/reanalysis inputs | Real external weather input used by the project | Household demand is measured because weather is real |
| Forecast | Frozen Stage 6B forecast output | Expected demand for the frozen retrospective origin/window | Exact future stochastic spike prediction |
| Quantiles and peak risk | Frozen Stage 6A/6B ensemble outputs | P10/P50/P90/P95 uncertainty and probability-based high-demand potential | Deterministic peak event |
| Explanations | Frozen Stage 6B primary/secondary fields | Direct backend explanation for the displayed forecast/risk hour | Newly generated AI explanation |
| Flexibility | Frozen Stage 7B production contract with Stage 3 event instances | Actual realized energy, duration, power, windows, dependencies, EV availability and boundary accounting | Ivana midpoint/mock examples as authoritative optimizer inputs |
| Optimized schedule | Frozen Stage 9 outputs | Modeled service preservation; minimum occupied comfort violation before cost/peak objectives | Universal comfort guarantee or a new optimization run |
| PV production | Frozen Stage 8 PVGIS model | Modeled annual production and linear capacity comparisons | Roof-measured production or system-sizing recommendation |
| Economics | Frozen Stage 10 outputs | `ANNUALIZED ESTIMATE` using the frozen hybrid annualization; `SIMPLE PAYBACK` | Measured annual economics, NPV, or lifecycle return |

## Cross-stage consistency

- Stage 3 totals equal the app historical totals.
- Stage 6B point forecasts, quantiles, temperatures, total expected energy, selected models, origins, and rankings equal the app forecast values.
- Stage 6A/6B probabilities, labels, and risk rankings equal the app peak-risk values.
- Stage 7B production constraints equal the app flexibility values.
- Stage 9 current, optimized, shifted-event, service, and comfort values equal the app optimizer values.
- Stage 8 production and Stage 10 economic rows equal the app PV values.
- The tariff is identical in the app and Stages 9/10, including 00:00, 06:00, 17:00, and 22:00 boundaries.
- Units, Europe/Madrid timestamps, observed versus annualized periods, and current versus optimized semantics remain distinct.
- The €1,162.52/year no-PV behavioral optimization benefit is separated from PV and combined benefits.

“Real backend output” means a real artifact produced by the WattWise project backend. It does not mean real-world measured household electricity data.
