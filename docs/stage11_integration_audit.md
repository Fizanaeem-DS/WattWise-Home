# Stage 11 application audit and integration map

## Existing application audited

The current repository did not contain the app shell. The previously supplied
`wattwise_ivana_branch (1).zip` contained Ivana's authoritative starting point:

- eight Streamlit pages: Overview, Historical Consumption, Forecast, Peak
  Hours, Tariff, Flexibility (Stage 7), PV Simulator, and Optimizer;
- a single `app/data_source.py` backend swap point;
- shared `theme.py`, `charts.py`, and `suggestions.py` components;
- a draft app transport contract;
- a mock generator that populated every dynamic page.

Stage 11 imports and preserves the page order, sidebar navigation, chart theme,
data-source abstraction, provenance badge pattern, and useful display
components. It does not import the mock generator.

## Mock and real data audit

| Existing page | Ivana branch before Stage 11 | Final real source |
|---|---|---|
| Overview | mixed values assembled from mock envelope | Stage 3C, latest complete Stage 6B 24-hour window, Stage 9 summary, Stage 10 5-kWp reference row |
| Historical Consumption | `mock_data.generator` | `data/processed/stage3c_household_hourly.csv` |
| Forecast | mock 24/72/168-hour bundles | latest complete window per horizon from `data/processed/stage6b_forecast_explained.csv` |
| Peak Hours | mock rankings and explanations | Stage 6B point forecast, Stage 6A quantiles/probability, Stage 6B labels and deterministic explanations |
| Tariff | fixed real challenge constant | same frozen official tariff used by Stages 6B, 9, and 10 |
| Flexibility | Stage 7 static display rules, including representative values | `stage7/artifacts/stage7b_optimization_requirements.json`, including real event-instance ranges |
| PV Simulator | mock savings/payback options | Stage 8 production as carried into Stage 10 plus Stage 10 capacity comparison and decomposition |
| Optimizer | illustrative placeholder schedule | frozen Stage 9 hourly comparison, event schedule, and optimizer summary |

There is no mock or silent fallback in the final data source. A missing required
artifact raises a clear runtime error before a final page is rendered.

## Schema mismatches resolved in the Stage 11 adapter

Ivana's early draft contract did not include forecast quantiles, continuous
peak probability, presentation risk labels, primary/secondary explanations,
real Stage 7 event-instance metadata, Stage 9 PV/grid/export/load metrics, or
the two-behavior Stage 10 economics. Frozen upstream contracts were not
changed. `src/hackowatt_stage11/models.py` defines a presentation-facing
adapter contract, and `src/hackowatt_stage11/loader.py` performs read-only,
fail-closed translation from the frozen artifacts.

## Horizon and timestamp semantics

The app selects the most recent complete historical-evaluation window for each
frozen Stage 6B horizon:

- 24 hours: origin `2025-09-28T23:00:00+02:00`;
- 72 hours: origin `2025-09-25T23:00:00+02:00`;
- 168 hours: origin `2025-09-22T23:00:00+02:00`.

Each window must contain exactly one row for every one-based lead hour. All
timestamps are timezone-aware Europe/Madrid values. The UI identifies these as
retrospective operational forecasts and does not expose realized future demand
as an operational input.

## Provenance semantics

Every dynamic page is marked REAL and lists its source artifacts. REAL means
the value came from the frozen project backend rather than placeholder app
data; it does not claim that the simulated household is real-world measured
data. `app/data_source.py` is the only UI backend entry point.

## Economic labeling

The PV page visibly labels all Stage 10 yearly household/economic results
`ANNUALIZED ESTIMATE`, explains the 61-day limitation, labels payback `SIMPLE
PAYBACK`, and keeps behavioral optimization benefit separate from PV benefit.
The 3, 5, 8, and 10 kWp capacities are comparisons, not recommendations.

## Run and validate

Install `requirements-stage11.txt`, then run:

```powershell
$env:PYTHONPATH = ".;src"
streamlit run app/app.py
python scripts/run_stage11_validation.py
python -m unittest -v tests.test_stage11_app_integration
```

Stage 11 never regenerates or writes Stage 1–10 artifacts.

## Remaining limitations

- Forecast screens show the latest complete frozen retrospective-evaluation
  window; no live weather/forecast feed is introduced.
- Historical household data covers 61 days, August–September 2025.
- Annual household/economic values are Stage 10 annualized estimates; annual
  PV production is the frozen Stage 8 PVGIS result.
- The app is read-only with respect to optimization. It displays the frozen
  Stage 9 result and does not provide a new solve endpoint.
- Deployment/hosting and Stage 12 submission packaging are outside Stage 11.
