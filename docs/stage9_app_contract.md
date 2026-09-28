# Stage 9 application contract

## Public entry points

`hackowatt_stage9.optimize_retrospective(capacity_kwp=5.0)` returns the solved frozen Aug-Sep retrospective realization, event schedule, HVAC trajectory, comfort proofs, and objective values.

`hackowatt_stage9.build_operational_context(forecast_origin, horizon_hours, capacity_kwp)` returns forecast-only operational inputs. The caller must provide event requirements that were known at the forecast origin. This function does not open Stage 3 actual-demand data.

`hackowatt_stage9.pipeline.run(verify_determinism=True)` runs the full retrospective optimizer, validation gates, second-solve determinism check, CSV/JSON export, and SVG generation.

## Hourly CSV

`data/processed/stage9_hourly_current_vs_optimized.csv` has one row for each of the 1,464 frozen Aug-Sep hours. Its stable fields are:

- `timestamp`
- `current_load_kwh`, `optimized_load_kwh`, `pv_generation_kwh`
- `tariff_eur_per_kwh`
- current/optimized `self_consumed_pv_kwh`, `grid_import_kwh`, `exported_pv_kwh`, and `net_cost_eur`
- `current_peak_risk`, `stage6_expected_demand_kwh`, `stage6_p95_kwh`
- optimized indoor temperature, heating/cooling duty fractions, and occupied comfort violation

The same PV value and accounting equations are used on both sides.

## Event CSV

`data/processed/stage9_event_schedule.csv` contains every Stage 7B event plus one HVAC aggregate row. It exposes actual and optimized start/end, energy, duration, power, shift, status, dependency, vehicle, deadline, availability, latest start, coherent-cycle flag, and same-day flag. `constraint_status` is `satisfied`, `boundary_outside_window`, or the HVAC comfort-proof status; no infeasible event is silently omitted.

Actual Stage 3 event values remain authoritative. Application code must not substitute static/mock values when this event contract exists.

## Summary JSON

`data/processed/stage9_optimizer_summary.json` contains:

- whole-period and representative-week energy/economic metrics;
- event counts and boundary/infeasibility reporting;
- service-preservation and comfort proof details;
- current Stage 3 versus optimized comfort statistics;
- operational/retrospective separation;
- every validation gate and the frozen-upstream identity;
- deterministic schedule hashes and solver objective values.

## UI integration rules

- Label the 5 kWp results as a reference scenario, never a sizing recommendation.
- Label Aug-Sep results as retrospective validation.
- Do not present Stage 6B forecasts as future actuals.
- Display exact `constraint_status` and boundary events.
- Keep EMPTY/AWAY thermostat values described as controller targets, not guaranteed indoor-temperature bounds.
- Describe positive occupied violations only as physically unavoidable when the matching proof is present.
- Do not infer battery operation or Stage 10 economics; neither exists in Stage 9.
