# Stage 6B WattWise app contract

## Operational hourly output

`data/processed/stage6b_forecast_explained.csv` has one row per evaluated forecast timestamp and window. It contains 2,232 rows across 27 windows. Field order and meaning are fixed:

| Field | Type | Meaning |
|---|---:|---|
| `timestamp` | ISO-8601 string | Forecast target time with UTC offset |
| `forecast_origin` | ISO-8601 string | Information cutoff and window origin |
| `horizon_hours` | integer | 24, 72, or 168 |
| `lead_hour` | integer | One-based hour within the window |
| `stage5_selected_model` | string | Frozen Stage 5 selected-model identifier |
| `point_forecast_kwh` | number | Frozen Stage 5 expected demand |
| `p10_kwh` | number | Frozen Stage 6A ensemble 10th percentile |
| `p50_kwh` | number | Frozen Stage 6A ensemble median |
| `p90_kwh` | number | Frozen Stage 6A ensemble 90th percentile |
| `p95_kwh` | number | Frozen Stage 6A high-demand potential (P95), not a maximum |
| `peak_threshold_kwh` | number | Frozen origin-specific Stage 6A peak threshold |
| `peak_probability` | number | Frozen Stage 6A ensemble exceedance probability |
| `peak_risk_label` | enum | `LOW`, `MEDIUM`, or `HIGH`; presentation only |
| `temperature_2m` | number | Frozen Stage 2 outdoor temperature in °C |
| `is_weekend` | boolean | Calendar weekend flag |
| `behavioral_block` | string | Frozen Stage 6A time block |
| `tariff_eur_per_kwh` | number | Frozen challenge tariff |
| `tariff_period` | string | Stable tariff-period identifier |
| `primary_explanation` | string | First deterministic probabilistic explanation |
| `secondary_explanation` | string | Optional second explanation, otherwise empty |
| `point_forecast_source` | string | Always `stage5_frozen_selected_model` |
| `risk_quantile_source` | string | Always `stage6a_frozen_ensemble` |
| `explanation_source` | string | Always `stage6b_deterministic_rules` |
| `provenance` | string | Always `real`, as defined below |

There is deliberately no actual-demand or realized-event field in this operational output.

## Per-window summaries

`data/processed/stage6b_forecast_summaries.json` contains a top-level metadata object and a `summaries` array. Each summary includes:

- `horizon_hours`, `forecast_origin`, and `total_expected_energy_kwh`
- `highest_expected_demand_hour` and `highest_expected_demand_kwh`
- `highest_peak_risk_hour`, `highest_peak_probability`, and `highest_peak_risk_p95_kwh`
- `number_low_risk_hours`, `number_medium_risk_hours`, and `number_high_risk_hours`
- `top_5_expected_demand_hours` and `top_5_peak_risk_hours`
- the three source identifiers and `provenance`

Each ranked item includes its timestamp, lead hour, expected demand, P95, continuous probability, display label, and at most two explanations. Expected-demand and peak-risk lists are distinct rankings.

## Provenance semantics

`provenance = "real"` means that the row was produced by the project backend instead of being placeholder or demo app data. It does **not** claim that the synthetic household is real-world measured data. The source fields disambiguate the frozen Stage 5 point forecast, frozen Stage 6A risk/quantiles, and deterministic Stage 6B explanation.

## Demo artifact

`artifacts/stage6b/168h_explained_forecast_demo.svg` is a diagnostic for the forecast origin `2025-09-13T23:00:00+02:00`. It shows Stage 5 expected demand, the Stage 6A P10–P90 band and P95, the top five peak-risk timestamps, and actual demand solely as labeled retrospective evaluation truth. The actual series is not part of either operational contract file.

