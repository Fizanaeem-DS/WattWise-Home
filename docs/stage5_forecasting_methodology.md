# Stage 5 household electricity-demand forecasting

## Scope and frozen inputs

Stage 5 forecasts frozen Stage 3C `household_total_kwh` for 24, 72, and 168
hours. The source fingerprint is pinned to
`fde362de6c8d758af02efe02110741e8c1bc352b6ed3030441038804a2a8c54a`.
Stage 4 JSON fingerprints are also recorded and tested. No Stage 1-4 artifact
is regenerated or changed, and Stage 6 is not started.

## Information boundary

Forecasts may use observed household demand only through their forecast origin.
Future predictors are restricted to timestamp-derived calendar variables and
four weather fields: temperature, relative humidity, cloud cover, and shortwave
radiation. Historical evaluation uses realized frozen Stage 2 weather as a
perfect-weather proxy, so reported errors exclude operational weather-forecast
error.

Future occupancy, AWAY, guests, components, EV charging, sauna, pool schedules,
HVAC mode, and indoor temperature are forbidden. They never enter a feature
matrix or final forecast contract.

## Features

The compact calendar/weather set is:

- sine/cosine of hour
- sine/cosine of weekday
- weekend indicator
- sine/cosine of day of year
- temperature
- relative humidity
- cloud cover
- shortwave radiation

The history-aware set adds lags 1, 2, 3, 24, 48, and 168 hours plus strictly
trailing means over the preceding 3, 6, and 24 hours. Training examples use
only values earlier than their targets.

## Models and fixed hyperparameters

No scikit-learn or XGBoost installation is available, so Stage 5 uses a small,
deterministic NumPy implementation:

- `M1_GBT_CAL_WEATHER`: gradient-boosted depth-2 regression trees; 40 trees,
  learning rate 0.05, minimum leaf size 20; calendar/weather features
- `M2_GBT_HISTORY`: the same boosted-tree defaults with history features
- `R2_RIDGE_HISTORY`: ridge regression with standardized features and alpha 10

These conservative settings were fixed before reviewing September results. No
hyperparameter search was performed. The implementation is deterministic; seed
`20251002` is recorded for the Stage 5 reproducibility contract even though the
chosen algorithms do not sample.

All learned-model predictions use the documented non-negative rule
`max(0, raw_prediction)`.

## Leakage-safe recursive strategy

Each learned model is trained as a one-step regressor on observations available
through an origin. M1 needs no target history. For M2 and ridge, forecasting is
sequential: after crossing the origin, lag or trailing features reference prior
predictions whenever their timestamp is after the origin. Actual future demand
is never read. Prediction rows preserve the maximum actual target reference,
recursive-reference count, and an explicit future-target-use audit flag.

The compatible B1 previous-day baseline is recursive beyond lead 24, repeating
its own prior predictions rather than reading actual post-origin demand. B2
uses the previous week, which remains observable through lead 168. B3 rebuilds
its hour-of-week means from observations available at each origin only.

## Rolling-origin evaluation

Origins begin at `2025-09-01T23:00:00+02:00` and advance every 72 hours.
Complete-window requirements yield:

- 24h: 10 origins / 240 forecast observations per model
- 72h: 9 origins / 648 observations per model
- 168h: 8 origins / 1,344 observations per model

Overlapping longer-horizon windows are intentional: they provide multiple
regularly spaced origins while preserving chronological training. Each origin
re-trains using only data available through that origin. All model/baseline
comparisons within a horizon use identical origin/timestamp pairs.

## Metrics and selection

Hourly metrics are MAE, RMSE, and WAPE. Every window also produces absolute and
signed period-total percentage error, top-10% timestamp overlap, and peak-
magnitude absolute error. Metrics are aggregated across origins, with per-origin
WAPE stability retained.

No weighted selection score is used. Evidence supports separate approaches:

- 24h: `M2_GBT_HISTORY`, because it has the best WAPE/MAE, total-energy error,
  bias, and peak overlap; M1 retains modest RMSE/peak-magnitude advantages.
- 72h and 168h: `M1_GBT_CAL_WEATHER`, because it is more stable and has the best
  overall hourly and total-energy errors. M2's recursive history accumulates
  material negative bias at longer horizons.

This is the frozen HackoWatt Stage 5 forecaster, not a production-ready model.

## Artifacts

The predictions CSV includes every candidate and compatible baseline, actuals,
forecast origin, horizon, lead, weather/calendar context, clipping flag, and
information-boundary audit fields. Thirty serialized rolling-origin models
reproduce evaluation predictions. Full-data M1 and M2 artifacts contain model
state, preprocessing, feature order, cutoff, recursive strategy, and training
sample count. The forecast contract exposes no hidden future twin state.

Eight SVG diagnostics under `artifacts/stage5_forecasting/` cover representative
windows, WAPE, peak retention, period totals, lead error, and baseline
comparison. They are development artifacts, not Stage 6 or app graphics.
