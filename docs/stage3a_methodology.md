# Stage 3A base and routine digital-twin loads

## Scope

Stage 3A generates only the household state/behavior layer and these electricity
components:

- refrigerator/freezer
- smart-home/base infrastructure
- cooking
- dishwasher
- washer and dryer
- daytime and evening electronics
- phone/tablet charging
- interior lighting
- exterior/security lighting

It does not generate HVAC, EV, pool-circulation, pool-heating, or sauna
electricity. Those major systems are reserved for Stage 3B.

## Inputs and reproducibility

- Frozen behavior: `docs/STAGE1_FROZEN_SPEC.md`
- Frozen timeline/weather: `data/processed/stage2_barcelona_weather_solar_hourly.csv`
- Random seed: `20250930`
- Timezone: `Europe/Madrid`
- Timeline: 2025-08-01 00:00 through 2025-09-30 23:00, 1,464 rows

All sampling uses Python's dedicated `random.Random(20250930)` instance.
Household parameters marked "sample once" are sampled once for the complete
61-day history. Events use continuous timestamps and allocate power/energy to
each hourly interval according to exact temporal overlap.

## Outputs

### Hourly dataset

`data/processed/stage3a_base_routine_hourly.csv`

It retains separate state, event-presence, component-energy, and total columns.
`day_type` is the effective hourly state (`WD_HOME`, `WE_HOME`, or `AWAY`), while
`base_day_type` preserves weekday/weekend context. Exact household departure and
return timestamps remain available even though `occupancy_state` is represented
at each hour's midpoint.

### Event ledger

`data/processed/stage3a_event_ledger.json`

The ledger preserves AWAY events, guest events, daily occupancy schedules, and
every generated appliance event. Each appliance record contains its sampled
energy, duration, start/end timestamps, average power, dependency where
applicable, and per-hour energy allocations. This lets later optimization use
the actual generated dishwasher/washer/dryer requirement rather than a generic
range or midpoint.

### Metadata and validation

- `data/processed/stage3a_metadata.json`
- `data/processed/stage3a_validation_report.json`

Metadata records the seed, household samples, state/event counts, AWAY coverage,
component totals, and total Stage 3A energy. Validation checks the timeline,
units of state, component arithmetic, frozen ranges, AWAY behavior, event
dependencies, exact energy preservation, and absence of Stage 3B columns.

## Boundary handling

AWAY events extending beyond the frozen history are clipped as required and
marked `boundary_clipped`. Other generated energy services are committed only
when their complete sampled requirement fits within the frozen timeline. On the
last date, this only restricts the feasible dishwasher start support enough to
retain the full sampled cycle energy.

The refrigerator uses a fixed +/-8% sinusoidal within-day profile. Its 24
weights are normalized, so each date sums back to the one sampled household
daily energy. This is within the frozen +/-10% limit and introduces no hourly
random drift.

