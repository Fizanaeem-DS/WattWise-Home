# HackoWatt Scenario 3 - Stage 5

This repository contains the frozen Stage 1 household specification, the Stage 2
Barcelona weather and solar pipeline, and Stage 3A base/routine digital-twin
loads. Stage 3B adds HVAC, two EVs, pool circulation, pool heating, and sauna.
Stage 3C combines the frozen Stage 3A and Stage 3B loads into the authoritative
61-day household historical profile. Stage 4 performs the read-only digital-
twin validation gate. Stage 5 adds leakage-safe 24/72/168-hour household-demand
forecasting. Stage 6 and all later stages are not implemented.

## Reproduce the dataset

The pipeline uses only the Python standard library (Python 3.10 or newer):

```powershell
python scripts/run_stage2.py
python -m unittest discover -s tests -v
```

The acquisition requests Open-Meteo's Historical Weather API with the explicit
ERA5 model, Barcelona city-centre coordinates, and `Europe/Madrid`. The raw JSON
response is preserved byte-for-byte under `data/raw/`; processed values are not
imputed or converted.

The Stage 3 input is:

`data/processed/stage2_barcelona_weather_solar_hourly.csv`

## Reproduce Stage 3A

```powershell
python scripts/run_stage3a.py
python -m unittest discover -s tests -v
```

The Stage 3A hourly artifact is:

`data/processed/stage3a_base_routine_hourly.csv`

Actual generated service requirements and fractional-hour allocations are kept
in `data/processed/stage3a_event_ledger.json`.

## Reproduce Stage 3B

```powershell
python scripts/run_stage3b.py
python -m unittest discover -s tests -v
```

The Stage 3B hourly artifact is:

`data/processed/stage3b_major_systems_hourly.csv`

Its exact EV, pool, and sauna events are recorded in
`data/processed/stage3b_event_ledger.json`. Stage 3B intentionally excludes
Stage 3A energy; their authoritative combination is reserved for Stage 3C.

## Reproduce Stage 3C

```powershell
python scripts/run_stage3c.py
python -m unittest discover -s tests -v
```

The authoritative combined historical profile is:

`data/processed/stage3c_household_hourly.csv`

Stage 3C is deterministic and introduces no new behavioral sampling. Its
metadata contains descriptive diagnostics only. Stage 4 assesses credibility
without tuning or changing the frozen twin.

## Run Stage 4 validation

```powershell
python scripts/run_stage4.py
python -m unittest discover -s tests -v
```

Stage 4 writes validation, baseline, and classification JSON artifacts under
`data/processed/` and ten diagnostic SVG figures under
`artifacts/stage4_validation/`. It does not modify the frozen Stage 3 profile or
train a forecasting model.

## Run Stage 5 forecasting

```powershell
python scripts/run_stage5.py
python -m unittest discover -s tests -v
```

Stage 5 writes rolling-origin predictions and model/baseline metrics under
`data/processed/`, serialized models under `models/stage5/`, and eight SVG
diagnostics under `artifacts/stage5_forecasting/`. It uses realized Stage 2
weather as an explicitly documented perfect-weather proxy during historical
evaluation and does not start Stage 6.

See `docs/stage2_requirements.md` for the official-document findings and
`docs/stage2_data_dictionary.md` for source definitions, units, processing, and
validation rules. See `docs/STAGE1_FROZEN_SPEC.md` for frozen behavior and
the Stage 3A, Stage 3B, and Stage 3C methodology documents for their respective
implementation boundaries.


