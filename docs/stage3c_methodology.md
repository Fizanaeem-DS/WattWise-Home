# Stage 3C final combined digital twin

## Scope and authority

Stage 3C is a deterministic integration and reconciliation layer. It joins the
frozen Stage 2, Stage 3A, and Stage 3B hourly artifacts one-to-one by their exact
timestamp strings and creates the authoritative 61-day historical household
electricity profile. It does not generate events, use an RNG, interpolate,
resample, scale, smooth, normalize, or add residual demand.

The generator stops if any source has other than 1,464 rows, if the three
timestamp sequences differ, if required source columns are absent, or if the
duplicated Stage 3A/3B occupancy and AWAY states disagree.

## Source immutability and reproducibility

The seven authoritative Stage 2/3A/3B artifacts are read-only. Stage 3C
metadata records a SHA-256 fingerprint for every input. Acceptance tests
regenerate the Stage 3C outputs into a temporary directory, require byte-for-
byte equality, and confirm that all source fingerprints remain unchanged.

There is no Stage 3C seed because Stage 3C contains no stochastic operation.

## Exact energy reconciliation

For every row, decimal arithmetic computes:

```text
household_total_kwh = stage3a_total_kwh + stage3b_total_kwh
```

The two source totals and every underlying Stage 3A/3B component are copied as
their original serialized values. The derived category views are:

- `base_fixed_kwh`: refrigerator plus smart-home base
- `routine_behavior_kwh`: the remaining Stage 3A routine components
- `hvac_kwh`: frozen Stage 3B HVAC total
- `ev_kwh`: frozen Stage 3B EV total
- `pool_kwh`: circulation plus pool heating
- `sauna_kwh`: frozen Stage 3B sauna load

Because frozen source stage totals and their source components were serialized
after independent rounding, their two equivalent reconciliation paths can
differ by at most `1e-9` kWh in an hourly row. The authoritative household total
always remains the exact decimal sum of the two frozen stage-total fields; the
category view is validated at the strict `1e-9` kWh tolerance.

## Preserved context

The final CSV includes all frozen Stage 2 weather and solar variables, Stage 3A
day/occupancy/AWAY/guest context, Stage 3B indoor temperature, HVAC targets and
mode, EV home state and home fraction, all source electricity components, both
stage totals, the derived category views, and the combined household total.
`temperature_2m` is the single canonical outdoor-temperature field; the
equivalent Stage 3B display alias is intentionally not duplicated.

## EV observation boundary

Only EV energy allocated inside the 1,464-hour window is present in the final
profile. The frozen Stage 3B ledger remains authoritative for the complete
physical requirement. Stage 3C metadata records the count and remaining energy
of boundary-truncated events and explicitly marks that remainder as outside the
historical profile. No row is appended and no energy is shifted backward.

## Existing variability inventory

Stage 3C introduces no additional randomness. Day-to-day differences already
exist because of:

- weekday/weekend structure
- `EMPTY`, `PARTIAL`, and `FULL` daytime occupancy
- exact AWAY episodes
- guest events
- cooking occurrence and timing
- dishwasher occurrence and timing
- laundry occurrence and timing
- electronics occurrence and timing
- weather-driven HVAC
- EV trip and charging variability
- pool-circulation runtime and window variability
- temperature/occupancy/guest-driven pool-heating activation
- sauna selected-day variability

## Outputs and validation boundary

- `data/processed/stage3c_household_hourly.csv`
- `data/processed/stage3c_metadata.json`
- `data/processed/stage3c_validation_report.json`

Metadata provides descriptive hourly, daily, weekday/weekend, AWAY/non-AWAY,
category-share, and top-ten peak diagnostics. These values do not alter the
profile and are not a Stage 4 credibility judgment. Physical, behavioral, and
statistical face validation remains explicitly deferred to Stage 4.
