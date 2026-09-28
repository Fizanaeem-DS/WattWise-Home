# Stage 5B targeted peak-aware forecasting experiment

## Scope and status

Stage 5B is a controlled experiment against the frozen Stage 5 benchmark. It
does not change Stages 2–5, does not replace a selected Stage 5 model, and does
not start Stage 6. Frozen Stage 3C, Stage 4, and Stage 5 artifacts are checked
against pinned SHA-256 fingerprints before and after every experiment run.

## Information boundary

The candidate uses the same features as Stage 5 M2:

- timestamp-derived calendar variables;
- the four Stage 5 weather variables (`temperature_2m`,
  `relative_humidity_2m`, `cloud_cover`, and `shortwave_radiation`); and
- leakage-safe demand lags at 1, 2, 3, 24, 48, and 168 hours plus trailing
  means over 3, 6, and 24 hours.

Realized frozen Stage 2 weather remains the Stage 5 perfect-weather proxy.
No future occupancy, guest, HVAC, indoor-temperature, EV, sauna, pool,
appliance, or event-ledger state is used. The target history contains observed
`household_total_kwh` only through the forecast origin. For later forecast
steps, prior Stage 5B predictions recursively replace unavailable actuals.

## Origin-specific regime definition

At each frozen Stage 5 forecast origin, the high-demand threshold is the 90th
percentile of all `household_total_kwh` observations at or before that origin.
The complete dataset is never used to set an earlier threshold. Across the 10
origins, thresholds range from 3.112946173 to 4.764862006 kWh. After the
168-hour feature warm-up, the separate high-regime regressors have 55–122
training observations; this exceeds the predeclared minimum of 40.

## Fixed two-stage candidate

Stage A is deterministic, unweighted L2 logistic regression. Features are
standardized from origin-available training rows. The fixed settings are
`alpha=1`, at most 50 Newton iterations, and convergence tolerance `1e-10`.
Unweighted logistic probabilities are used so the output remains suitable as
a mixture probability. No hyperparameter search is performed.

Stage B fits two deterministic gradient-boosted tree regressors. The normal
model uses 40 trees, learning rate 0.05, depth 2, and minimum leaf size 20. The
smaller high-regime model uses the same settings except minimum leaf size 8.
Both models are trained only on targets at or before the origin, partitioned by
that origin's threshold. The forecast is:

`(1 - P_high) * normal_prediction + P_high * high_prediction`

The combined result is clipped to zero. Models are refitted at each origin and
saved separately under `models/stage5b/evaluation/` with their threshold,
training cut-off, counts, features, and serialized parameters.

## Evaluation

The horizons, forecast origins, and forecast timestamps exactly match frozen
Stage 5. Stage 5B is compared with the frozen selected model, the other required
M1/M2 candidate, and B3 on the same forecast instances. Load, period-energy,
top-10% peak, and peak-magnitude metrics use the frozen Stage 5 definitions.

For high-demand precision, recall, and F1, an actual or predicted load is high
when it is at least the 90th-percentile threshold learned for that forecast
origin. This applies the same origin-specific, history-only boundary to actual
and predicted demand and does not use a global future-informed threshold.

## Result and acceptance decision

| Horizon | Stage 5B WAPE | Frozen selected WAPE | Stage 5B peak overlap | Frozen overlap | Stage 5B peak-magnitude MAE | Frozen peak-magnitude MAE |
|---:|---:|---:|---:|---:|---:|---:|
| 24h | 109.601951% | 72.833190% | 33.333333% | 40.000000% | 5.541737 kWh | 4.806897 kWh |
| 72h | 91.200387% | 71.268171% | 37.500000% | 41.666667% | 5.767520 kWh | 7.922152 kWh |
| 168h | 88.531769% | 71.118304% | 35.294118% | 41.176471% | 7.927031 kWh | 10.387599 kWh |

Stage 5B raises high-demand recall at every horizon and improves peak-magnitude
error at 72h and 168h, including the audited Sep-13 window. However, MAE, RMSE,
WAPE, and period-energy error are materially worse at every horizon; peak
overlap is worse at every horizon; and high-demand F1 is worse at 72h and 168h.
The experiment is therefore classified **NO USEFUL IMPROVEMENT**. Stage 5B
should not be promoted, and frozen Stage 5 remains authoritative.

## Reproduction

Run:

```powershell
python scripts/run_stage5b.py
python -m unittest discover -s tests -v
```

The Python executable may need to be addressed by its installed path when it
is not on `PATH`. The experiment writes only `stage5b_*`, `artifacts/stage5b/`,
and `models/stage5b/` outputs.

