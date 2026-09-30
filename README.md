# WattWise Home

**HackoWatt 2026 — Scenario 3: Luxury Under Control**

WattWise Home is a smart-home energy management prototype for a high-consumption Barcelona household. It combines an hourly household digital twin, real historical weather, multi-horizon demand forecasting, probabilistic peak-risk analysis, appliance flexibility constraints, solar modelling, and constrained scheduling optimization to turn energy predictions into explainable household decisions.

**Live app:** https://wattwise-home-mql6vnwdup3xm9bs3phd5d.streamlit.app/

## The challenge

Anna and Robert live in a large smart home with two EVs, HVAC, a pool, sauna, and flexible household loads. WattWise was designed to answer four practical questions:

- What will the home consume over the next 24 hours, 3 days, and 7 days?
- When is high demand most likely, and what is driving it?
- Which activities can move without violating modeled comfort or service constraints?
- How do scheduling and rooftop solar change grid use, electricity cost, and peak demand?

## What WattWise does

WattWise connects the full decision pipeline:

```text
Household specification + Barcelona weather
                    ↓
        Scenario-specific digital twin
                    ↓
       24h / 72h / 168h forecasting
                    ↓
       Probabilistic peak-risk analysis
                    ↓
        Appliance flexibility model
                    ↓
             PV generation
                    ↓
   Comfort → Cost → Peak optimization
                    ↓
          Explainable WattWise Plan
```

The Streamlit application presents the system through four user-facing pages:

1. **Home** — next-24-hour demand, peak-risk signal, tariff context, and plan impact.
2. **My Energy** — historical consumption, upcoming demand, and peak-risk views.
3. **WattWise Plan** — original vs optimized schedules and the activities that were rescheduled.
4. **Solar** — 3, 5, 8, and 10 kWp PV comparison with grid, cost, self-consumption, and simple-payback estimates.

## Data foundation

The final Scenario 3 household profile is a **scenario-specific simulated digital twin**, not measured smart-meter data from a real Anna and Robert household.

- **61 days:** August–September 2025
- **1,464 hourly observations**
- **2,834.740 kWh** modeled household demand
- Major systems include **two EVs, HVAC, pool, sauna, routine loads, and base loads**
- Environmental inputs use **real historical Barcelona weather** from Open-Meteo/ERA5
- Solar modelling uses **PVGIS** production assumptions

Real REFIT household data was used during methodology development, but it is not presented as the final Scenario 3 household.

## Forecasting

Stage 5 evaluates:

- Gradient Boosted Regression Trees with calendar + weather features
- Gradient Boosted Regression Trees with calendar + weather + historical-demand features
- Ridge Regression with calendar + weather + historical-demand features
- Previous-day, previous-week, and hour-of-week temporal baselines

Evaluation uses **chronological rolling-origin validation rather than a random split** to protect the temporal structure and reduce leakage risk.

Selected models are horizon-specific:

- **24 h:** GBT with calendar, weather, and historical-demand features
- **72 h:** GBT with calendar and weather features
- **168 h:** GBT with calendar and weather features

Historical evaluation uses realized weather as an explicitly documented perfect-weather proxy.

## Peak-risk modelling

A separate uncertainty layer estimates high-demand risk rather than treating a smooth point forecast as a guaranteed future trajectory.

The peak-risk workflow uses a **200-member ensemble** and reports risk as LOW, MEDIUM, or HIGH. This lets the app distinguish expected demand from the probability of a high-demand event.

## Flexibility and constraints

The optimizer does not assume every appliance can be moved freely.

- **A — Fixed:** base loads and non-shiftable services
- **B — Behavior-driven:** activities such as cooking and entertainment
- **C — Limited flexibility:** HVAC, sauna, and pool
- **D — Shiftable:** EV charging, dishwasher, washer, and dryer

The production flexibility ledger contains **177 modeled flexible/limited event constraints**. EV charging uses each vehicle's next modeled departure as a deadline rather than a single fixed daily deadline.

## Optimization

WattWise uses a **lexicographic optimization** rather than a single blended score:

1. **Comfort** — minimize modeled occupied-hour HVAC comfort violations.
2. **Cost** — with the comfort optimum preserved, minimize net electricity cost.
3. **Peak** — with comfort and cost priorities preserved, minimize maximum hourly load.

This ordering prevents a cheaper schedule from being selected simply by sacrificing the modeled comfort objective.

## Reference results

For the **61-day, 5 kWp reference evaluation**, current vs optimized scheduling produced:

| Metric | Current | Optimized | Change |
|---|---:|---:|---:|
| Net electricity cost | €625.065 | €356.045 | **↓ 43.0%** |
| Maximum hourly load | 21.699 kWh | 9.880 kWh | **↓ 54.5%** |
| Grid import | 2,071.627 kWh | 1,663.413 kWh | **↓ 19.7%** |
| PV self-consumption | 763.114 kWh | 1,121.944 kWh | **↑ 47.0%** |

The application displays **172 rescheduled events** in this evaluation. This is distinct from the 177 production flexibility/limited event constraints.

## Solar and economics

PV production is based on Barcelona PVGIS data, with comparison cases at **3, 5, 8, and 10 kWp**. These capacities are comparison cases, not recommendations.

The project assumptions include:

- Installation: **€1,300/kWp**
- Export compensation: **€0.08/kWh**
- Annual O&M: **1%**
- Barcelona PV production: approximately **1,559 kWh/year/kWp**

Annual figures shown in the application are **annualized estimates**, and payback is **simple payback**.

## Repository structure

The project is organized as a staged pipeline so that household generation, validation, forecasting, risk, flexibility, solar, optimization, economics, and application integration remain separable and testable.

Key directories include:

- `src/` — pipeline and application logic
- `scripts/` — stage runners
- `tests/` — validation and contract tests
- `data/` — raw and processed pipeline artifacts
- `models/` — serialized forecasting artifacts
- `artifacts/` — diagnostic outputs
- `docs/` — methodology, requirements, and data documentation

## Reproducing the core pipeline

The repository contains stage-specific scripts and tests. Examples:

```powershell
python scripts/run_stage2.py
python scripts/run_stage3a.py
python scripts/run_stage3b.py
python scripts/run_stage3c.py
python scripts/run_stage4.py
python scripts/run_stage5.py
python -m unittest discover -s tests -v
```

Stage 2 acquires Open-Meteo historical weather using the ERA5 model, Barcelona coordinates, and `Europe/Madrid`. Stage 3 builds the component-level household twin. Stage 4 performs read-only validation. Stage 5 performs leakage-aware rolling-origin forecasting. Later repository stages implement the peak-risk, flexibility, PV, optimization, economics, and application workflow used by the final prototype.

See the `docs/` directory and stage-specific source/tests for implementation boundaries and assumptions.

## Limitations

WattWise is a hackathon prototype, so its outputs should be interpreted within the modeled assumptions:

- Household demand is scenario-specific simulated data rather than measured Anna/Robert smart-meter data.
- The household evaluation window covers 61 days rather than a full year.
- Annual economics are estimates derived from the evaluation period together with full-year PVGIS production.
- PVGIS represents modeled/long-term solar production rather than measurements from Anna and Robert's roof.
- Simple payback excludes financing, degradation, inflation, subsidies, and taxes.
- No battery is included.
- The prototype computes and explains schedules but does not directly control physical smart-home devices.

## HackoWatt 2026

WattWise Home was developed as a **HackoWatt 2026 submission** for **Scenario 3 — Luxury Under Control**.

The project focuses on connecting forecasting to decisions: predicting demand is only the first step; WattWise also models what can move, protects modeled comfort constraints, evaluates solar availability and tariffs, and produces an explainable optimized household schedule.

---

**Live demo:** https://wattwise-home-mql6vnwdup3xm9bs3phd5d.streamlit.app/
