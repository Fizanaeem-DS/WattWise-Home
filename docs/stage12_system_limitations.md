# Stage 12 final system limitations

These limitations are part of the final product claim boundary and must remain visible in any Stage 13 material.

- The Scenario 3 household is a scenario-specific synthetic digital twin, not measured Anna/Robert smart-meter data.
- The household realization covers 61 days: 2025-08-01 through 2025-09-30, with Europe/Madrid summer-time timestamps (`+02:00`).
- Household and economic yearly figures are `ANNUALIZED ESTIMATE`, not measured annual performance.
- Forecasts are frozen retrospective evaluation windows. They estimate expected demand and uncertainty; exact stochastic spikes cannot be predicted.
- Peak-risk probabilities and P95 are probabilistic high-demand-potential indicators, not deterministic peak promises.
- Weather/reanalysis inputs are real Barcelona data, but household demand remains synthetic.
- PV production is frozen PVGIS modeling, not generation measured on the actual roof.
- The 3, 5, 8, and 10 kWp systems are comparison capacities, not sizing recommendations.
- There is no battery model.
- The economics omit financing, discounting, degradation, inflation, subsidies, and taxes.
- `SIMPLE PAYBACK` is not NPV or lifecycle analysis.
- Stage 9 preserves modeled flexible services and introduces zero avoidable occupied HVAC comfort violation. It identifies 42 physically infeasible occupied hours with minimum unavoidable violations; this is not a universal real-world comfort guarantee.
- The optimizer and economics use frozen model assumptions and tariffs; results should not be generalized beyond this scenario without revalidation.
