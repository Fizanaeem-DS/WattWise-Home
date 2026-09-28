# Stage 10 PV investment and economics methodology

## Scope

Stage 10 compares rooftop PV under current habits and the frozen Stage 9 optimized habits. It does not alter or recreate Stage 8 or Stage 9, does not select an “optimal” capacity, and does not start Stage 11.

The four capacities—3, 5, 8, and 10 kWp—are comparison cases. Five kWp remains the reference/demo case, not a recommendation.

## Authoritative inputs

- Frozen Stage 8 PVGIS 5.3 engine and artifacts: Barcelona 41.3874, 2.1686; crystalline silicon; fixed 30° tilt; PVGIS aspect 0° (south); free-standing/ventilated mounting; 14% losses; no tracking; terrain horizon enabled.
- Frozen Stage 8 annual production: 1,559.01 kWh/year/kWp, with its frozen monthly profile and Aug–Sep hourly shape.
- Frozen Stage 9 `stage9_hourly_current_vs_optimized.csv`: 1,464 hourly Europe/Madrid records from 2025-08-01 through 2025-09-30, with current and optimized load in kWh.
- Frozen Stage 9 tariff and accounting functions, imported directly rather than reimplemented.

Stage 10 checks authoritative file SHA-256 values and an independent 1,249-file Stage 1–9 tree hash before producing results.

## Exact observed Aug–Sep accounting

For each capacity and both behaviors, every frozen hour uses:

`self_consumed_pv = min(load, PV)`

`grid_import = max(load - PV, 0)`

`pv_export = max(PV - load, 0)`

`import_cost = grid_import × tariff`

`export_revenue = pv_export × €0.08/kWh`

`net_electricity_cost = import_cost - export_revenue`

The tariff is €0.18/kWh from 00:00–06:00, €0.28 from 06:00–17:00, €0.40 from 17:00–22:00, and €0.28 from 22:00–24:00 in Europe/Madrid local time. The current and optimized cases use identical PV, tariff, export compensation, and equations.

The 5 kWp results must reproduce all frozen Stage 9 aggregate self-consumption, grid import, export, and net cost within `1e-7`; the observed differences are only floating-point summation residue below `3.2e-12`.

## Annualization methodology

All annual values are labeled **ANNUALIZED ESTIMATE**. They are not measured annual household performance.

Only 61 days of household demand exist. Stage 10 therefore uses a two-part, symmetric annualization:

1. Annual household demand and each behavior’s no-PV tariff cost are the frozen 61-day values multiplied by `365/61`.
2. For each capacity and behavior, observed hourly matching determines PV self-consumption, export, avoided import cost, and export revenue per generated PV kWh. Each PV-driven quantity is multiplied by:

   `exact frozen annual PV production / observed Aug–Sep PV production`

This preserves the exact Stage 8 annual PV total, the observed hourly demand/PV coincidence, time-of-use value, and the energy identities:

`annual PV = annual self-consumption + annual export`

`annual demand = annual self-consumption + annual grid import`

It does not fabricate household demand for missing months. Its limitation is material: it assumes Aug–Sep demand timing, PV coincidence, and tariff value per PV kWh are representative of the year. Seasonal occupancy, HVAC, and coincidence patterns are unknown.

## Investment economics

For every capacity:

`initial investment = capacity × €1,300/kWp`

`annual O&M = 1% × initial investment`

The PV comparison always uses the matching behavior-specific no-PV baseline:

- current + PV versus current + no PV;
- optimized + PV versus optimized + no PV.

`gross annual electricity benefit = matching no-PV net cost - with-PV net cost`

`net annual PV benefit = gross annual electricity benefit - annual O&M`

`simple payback = initial investment / net annual PV benefit`

Simple payback is reported only when the net annual benefit is positive. No discounting, financing, degradation, inflation, subsidy, tax treatment, battery, or roof-specific shading is included.

PV self-consumption rate means `self-consumed PV / total PV generation`. Household solar coverage means `self-consumed PV / household demand`. These are reported separately.

## Fair decomposition

Stage 10 keeps four effects separate:

1. behavioral effect: current no PV → optimized no PV;
2. PV effect under current habits: current no PV → current + PV;
3. PV effect under optimized habits: optimized no PV → optimized + PV;
4. combined end state: current no PV → optimized + PV.

The decomposition is checked algebraically. Stage 9 behavioral savings are never counted as PV investment benefit, and optimization never changes installation cost or annual O&M.
