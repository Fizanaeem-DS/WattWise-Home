# Stage 3B major household systems

## Scope

Stage 3B generates only these major-system loads:

- binary rated-power HVAC heating and cooling
- EV1 and EV2 movement and home charging
- pool circulation
- pool heating
- sauna

It consumes the frozen Stage 2 timeline/weather and frozen Stage 3A states and
events. It does not resample or modify Stage 3A, combine Stage 3A and Stage 3B,
or implement any Stage 3C or Stage 7 optimization behavior.

## Inputs and reproducibility

- Frozen behavior: `docs/STAGE1_FROZEN_SPEC.md`
- Weather: `data/processed/stage2_barcelona_weather_solar_hourly.csv`
- Stage 3A hourly state: `data/processed/stage3a_base_routine_hourly.csv`
- Stage 3A events: `data/processed/stage3a_event_ledger.json`
- Stage 3A metadata: `data/processed/stage3a_metadata.json`
- Stage 3B random seed: `20251001`
- Timezone: `Europe/Madrid`
- Timeline: 2025-08-01 00:00 through 2025-09-30 23:00, 1,464 rows

All Stage 3B sampling uses a dedicated `random.Random(20251001)` instance, so
Stage 3A artifacts and random draws remain untouched. Household parameters are
sampled once; daily decisions and events are then sampled in a fixed order.

## Daily and exact-time behavior

The Stage 3B daily classification follows the frozen 23:00 rule. A date is
`AWAY_DAY` only when an exact Stage 3A AWAY interval is active at that date's
23:00 timestamp; otherwise its frozen weekday/weekend home class is retained.
Exact physical restrictions continue to use the original AWAY start and end
timestamps.

If an activated pool-heating or sauna block initially overlaps exact AWAY, only
its start is rejection-resampled inside the frozen current-behavior start range
(08:00-14:00 for pool heating, 19:00-22:00 for sauna). Duration, power, and
energy remain unchanged. Generation raises `NoFeasibleStartError` with the
date, system, and duration if the complete event has no feasible start; there
is no cancellation, truncation, or fallback policy.

## Energy allocation

Every continuous event is allocated by its exact overlap with each hourly
interval. Constant-power event energy is therefore `power_kw * overlap_hours`,
including fractional first and final hours. Normal events preserve required
energy exactly within numerical tolerance.

EV charging requirements that cross the observation boundary retain their full
required energy and physical end in the event ledger. Only in-window energy is
written to the hourly artifact, with the remainder recorded explicitly and
`boundary_truncated` set to true.

## Outputs

- `data/processed/stage3b_major_systems_hourly.csv`
- `data/processed/stage3b_event_ledger.json`
- `data/processed/stage3b_metadata.json`
- `data/processed/stage3b_validation_report.json`

The hourly artifact contains only Stage 3B state and energy. The authoritative
combined Stage 3A + Stage 3B household dataset remains deferred to Stage 3C.

## Validation

`scripts/run_stage3b.py` regenerates Stage 3B and writes the validation report.
The independent Stage 3B acceptance tests verify timeline identity, controller
and thermal recurrence behavior, EV availability and boundary accounting,
daily pool-circulation service, pool-heating and sauna probability structures,
fractional energy preservation, exact-AWAY exclusion, forced start-only
resampling for both affected systems, explicit failure when no feasible start
exists, and byte-identical deterministic regeneration. The full test discovery
also reruns the frozen Stage 2 and Stage 3A regression suites.
