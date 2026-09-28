# Stage 1 - Frozen Household Specification

This document is the authoritative implementation specification for the future
Stage 3 digital twin for HackoWatt Scenario 3. It operationalizes the official
challenge facts without replacing or modifying them.

## Provenance key

- **Official challenge fact:** stated in the official Scenario 3 or Common
  Challenge Assumptions PDF.
- **Frozen modelling assumption:** a project decision that Stage 3 must follow,
  but which must not be represented as an official challenge value.
- **Deferred/unresolved parameter:** intentionally not fixed here. It must be
  explicitly resolved before the affected implementation is written.

The authoritative official documents are:

- `HackoWatt-Scenario-3-Luxury-Under-Control.pdf`
- `HackoWatt-Common-Challenge-Assumptions.pdf`

If this operational specification ever conflicts with an official challenge
fact, the official document governs. Within the modelling choices made here,
this frozen specification governs Stage 3.

## 1. Scenario

**Provenance: official challenge facts.**

Scenario 3 - Luxury Under Control.

Household:

- Anna and Robert
- Barcelona, Spain
- 2 adults
- large detached smart home
- high standard of living
- swimming pool
- sauna
- air conditioning
- electric vehicles
- extensive smart-home infrastructure
- relatively high electricity consumption
- comfort maintained throughout the day

Goal: improve efficiency, use renewables better, and avoid waste without
reducing comfort.

This frozen specification operationalizes those official facts for the digital
twin.

## 2. Official appliance/system ranges

**Provenance: official challenge ranges.**

- Heat pump/electric heating: 1.5-4.0 kW during operation
- Air conditioning: 1.0-2.5 kW
- Refrigerator + freezer: 1.5-2.2 kWh/day
- Pool circulation: 0.6-1.2 kW
- Pool heating: 2.0-5.0 kW
- Sauna: 6.0-9.0 kW
- EV charger: up to 7.4 kW per vehicle
- Oven: 2.0-2.5 kW
- Induction hob: 1.5-4.0 kW
- Dishwasher: 0.8-1.2 kWh/cycle
- Washer: 0.6-1.0 kWh/cycle
- Dryer: 1.5-2.5 kWh/cycle
- TV: 0.10-0.20 kW
- Smart/garden lighting: 0.10-0.40 kW
- Smart-home infrastructure: 0.05-0.15 kW continuous
- Laptop/computer: 0.05-0.25 kW
- Phone/tablet: 0.005-0.02 kWh/device/charge

## 3. Base day types

**Provenance: frozen modelling assumptions.**

Use exactly three top-level day states:

- `WD_HOME` - weekday home-day behavior
- `WE_HOME` - weekend home-day behavior
- `AWAY` - genuine extended absence

`WD_HOME` does not mean the residents remain physically home all day. Normal
daytime absence may still occur.

`WE_HOME` represents weekend home-day behavior.

`AWAY` overrides `WD_HOME` and `WE_HOME` behavioral routines.

Retain calendar `is_weekend` separately as contextual information.

## 4. Household occupancy state

**Provenance: frozen modelling assumptions.**

Use household-level occupancy only.

States:

- `EMPTY` - neither resident home
- `PARTIAL` - some household presence, lower activity than `FULL`; do not
  assign an identity
- `FULL` - both residents home / normal full household activity possible

Do not model named individual occupancy for Anna versus Robert.

### Weekday daytime occupancy, 09:00-16:00

For `WD_HOME`:

- `EMPTY`: 70%
- `PARTIAL`: 20%
- `FULL`: 10%

### Weekend daytime occupancy

For `WE_HOME`:

- `EMPTY`: 20%
- `PARTIAL`: 30%
- `FULL`: 50%

Occupancy must form temporally coherent episodes. Do not independently redraw
occupancy every hour.

### Household departure/return timing

Weekday, where departure occurs:

- departure: 08:30-09:00
- return: 16:00-19:00

`EMPTY`:

- household departure/return timing applies

`PARTIAL`:

- departure/return applies to the portion of activity/presence that leaves
- do not assign resident identity

`FULL`:

- no daytime household departure

Weekend:

- `EMPTY`: depart 10:00-13:00, return 16:00-19:00
- `PARTIAL`: depart 10:00-13:00, return 15:00-19:00
- `FULL`: no household departure

### Hourly occupancy representation

**Provenance: frozen modelling assumption, not an official challenge value.**

- Preserve exact departure and return timestamps separately.
- Classify the hourly `occupancy_state` using the household state at the
  midpoint of that hourly interval (`HH:30`).
- Do not discard the exact event timestamps.

This midpoint rule is only an hourly representation rule. It does not change
the underlying departure/return event times.

## 5. AWAY behavior

**Provenance: frozen modelling assumptions.**

`AWAY` is a top-level override generated before normal occupancy/timing.

Approximately 5% of days initiate an `AWAY` event.

Conditional duration distribution:

- short/overnight: 70%
- approximately 1 full day: 20%
- approximately 2-3 days: 10%

### AWAY event timing operationalization

**Provenance: frozen modelling assumptions, not official challenge values.**

- Process eligible days chronologically.
- Do not initiate another `AWAY` event while an existing `AWAY` event is active.
- Sample start time uniformly between 06:00 and 20:00.
- Short/overnight duration: Uniform(12, 24) hours.
- Approximately one-full-day duration: Uniform(24, 36) hours.
- Approximately 2-3-day duration: Uniform(48, 72) hours.
- Preserve exact `away_start`, `away_end`, and `away_duration`.
- If an event extends beyond the Stage 2 dataset end, clip it at the dataset
  boundary and record `boundary_clipped = true`.
- Do not create overlapping `AWAY` events.

Represent explicitly:

- `away_start`
- `away_end`
- `away_duration`

Important: 5% refers to `AWAY` event starts, not the total percentage of days
covered by `AWAY`. Actual resulting `AWAY`-day coverage must later be measured
in Stage 4.

The 23:00 rule is only a transition-day classification threshold. Do not
interpret it as a normal household return time. The ordinary return generator
must not invent late normal returns such as 20:30 or 22:30.

### Stage 3B AWAY transition-day classification

**Provenance: frozen implementation assumption, not an official challenge
value.**

This rule applies only where Stage 3B requires a daily classification:

- if the household is in an active `AWAY` event at the calendar date's 23:00
  timestamp, classify the date as `AWAY_DAY` for daily Stage 3B decisions
- otherwise retain its normal `WD_HOME` / `WE_HOME` daily classification

Do not alter Stage 3A's exact hourly `AWAY` state or the exact event start/end
timestamps. Hourly physical availability continues to follow the exact interval.
A same-day `AWAY` event that begins and ends before 23:00 does not convert the
whole date into `AWAY_DAY`, although exact hourly restrictions still apply while
the event is active.

During `AWAY`, suppress:

- cooking
- TV / occupant electronics
- laundry
- dishwasher
- interior occupancy lighting

Continue:

- refrigerator/freezer
- smart-home/base infrastructure
- HVAC using `AWAY` setback
- pool circulation using the `AWAY` rule
- security/exterior lighting where applicable

Pool heating is off during `AWAY`.

EV behavior during `AWAY` follows the dedicated EV rules below.

## 6. EV system

**Provenance: frozen modelling assumptions except for the official maximum
charging power.**

Use exactly two EVs:

- `EV1`
- `EV2`

Do not assign named ownership.

Maximum charging power: 7.4 kW per EV. **This is an official challenge range.**

Each EV has its own daily presence/departure/return schedule. Departure and
return may be nullable if the vehicle does not leave.

### Ordinary WD/WE leave probabilities

Base probability that a vehicle leaves:

| Day type | EV1 | EV2 |
|---|---:|---:|
| `WD_HOME` | 70% | 60% |
| `WE_HOME` | 45% | 40% |

Apply household occupancy modifier:

- `EMPTY`: x1.15
- `PARTIAL`: x1.00
- `FULL`: x0.70

Cap the resulting probability at 1.0.

The compounding of day type and occupancy modifiers is intentional and frozen.
These occupancy modifiers are modelling assumptions, not official challenge
values.

### Charging requirement

If an EV was used, there is a 70% probability that it requires charging after
return.

Required charging-energy tier:

| Tier | Energy | Probability |
|---|---:|---:|
| `LOW` | 6-12 kWh | 45% |
| `MEDIUM` | 12-24 kWh | 40% |
| `HIGH` | 24-40 kWh | 15% |

Sample actual required energy continuously within the selected tier. Do not
create a detailed battery state-of-charge model.

### Current charging behavior

When charging is required:

- begin after return
- random delay: 0-60 minutes
- charging power while active: 7.4 kW
- cap the final interval to the remaining required energy
- otherwise EV charging load is 0
- charging may continue overnight into the following morning

Required charging must be feasible before the next departure. The digital-twin
generator must ensure feasibility.

### EV observation-boundary handling

**Provenance: frozen implementation assumption.**

Do not suppress, redraw, or shorten a legitimate EV charging requirement merely
because the observation window ends. If charging extends beyond the frozen
dataset boundary:

- preserve the complete physical requirement and intended trajectory/end in the
  event ledger where calculable
- preserve `required_energy_kwh`
- allocate only energy within the 1,464-hour observation window to the hourly
  Stage 3B dataset
- set `boundary_truncated = true`
- record `delivered_in_window_kwh` and `remaining_energy_kwh`
- require `required_energy_kwh = delivered_in_window_kwh +
  remaining_energy_kwh` within numerical tolerance

For non-boundary-truncated charging events, set `boundary_truncated = false`,
deliver the full requirement, and set `remaining_energy_kwh = 0`.

The frozen `AWAY` event ending at `2025-10-01T00:00:00+02:00` may create a
post-boundary requirement in the ledger but must not add an hourly row.

### Weekend EV trip timing

If selected to leave on a weekend:

- depart 09:00-14:00
- return 15:00-21:00
- return must be after departure
- perform a feasibility check for required charging

EV movement is separate from household departure/return timing.

### EV behavior during AWAY

Conditional `AWAY` vehicle state:

- both vehicles travel: 50%
- one vehicle travels: 40%
- both remain home: 10%

If one travels, select anonymously; do not assign resident identity.

Traveling EV:

- absent from home
- no home charging while away
- returns at `AWAY` end
- may require charging after return

Home-remain EV:

- no new trip requirement generated during `AWAY`
- pre-existing charging requirement may finish

Ordinary `WD_HOME`/`WE_HOME` EV generation and `AWAY` EV generation are mutually
exclusive. Do not independently apply ordinary EV departure logic during
`AWAY`.

## 7. Pool circulation

**Provenance: official power range; all scheduling and runtime rules are frozen
modelling assumptions.**

Sample pool-circulation power once for the household:

- Uniform(0.6, 1.2) kW

Daily required runtime:

- normal `WD_HOME` / `WE_HOME`: sample 6-10 hours/day
- `AWAY`: sample 4-6 hours/day

Runtime is sampled daily.

Represent runtime in one or two coherent windows. Do not scatter independent
random `ON` hours.

Frozen current-behavior window generation:

- after sampling required runtime, choose one window with 30% probability or
  two windows with 70% probability
- for one window, sample start uniformly between 08:00 and 12:00 and run
  continuously for the complete required runtime
- for two windows, sample the first start uniformly between 06:00 and 09:00 and
  the second start uniformly between 15:00 and 18:00
- allocate Uniform(0.50, 0.70) of total runtime to the first window and the
  exact remainder to the second
- preserve exact sampled runtime and energy
- if windows would overlap or extend beyond the calendar day, resample the start
  within the same permitted range where feasible; do not change required runtime

These are current-behavior schedules, not optimization schedules.

Circulation is treated as maintenance demand and is intentionally not
weather-dependent.

Normal `EMPTY`/`PARTIAL`/`FULL` occupancy does not turn circulation off.

`AWAY` reduces circulation runtime but does not eliminate it.

For later optimization:

- circulation may be shifted
- required runtime cannot be deleted
- all required runtime must be completed within the same calendar day

## 8. Pool heating

**Provenance: official power range; activation probabilities, modifiers, and
service rules are frozen modelling assumptions, not official challenge
values.**

Sample pool-heating operating power once:

- Uniform(2.0, 5.0) kW

On an active pool-heating day:

- duration: 2-5 hours
- use a coherent operating block
- sample current-behavior start uniformly between 08:00 and 14:00

This start rule applies only to current behavior and does not define the later
Stage 7 optimization window.

Activation probability depends on daily mean outdoor temperature calculated
from the real Stage 2 hourly Barcelona temperature:

- below 15°C: base daily activation probability = 0.70
- 15-20°C: base daily activation probability = 0.35
- above 20°C: base daily activation probability = 0.08

Occupancy/event modifiers:

- `FULL`: x1.25
- `PARTIAL`: x1.00
- `EMPTY`-heavy: x0.60
- guest event: x1.30
- `AWAY`: activation probability = 0 / off

Cap the final activation probability at 1.0.

Do not add a solar-radiation control term to pool-heating activation.

Barcelona August/September weather may legitimately produce rare or near-zero
pool-heating events. Do not artificially inflate pool heating merely to make the
dataset look more varied.

For later optimization:

- if a pool-heating service event exists, service must be preserved
- the exact feasible shifting window is deferred to Stage 7
- do not delete the service

## 9. Sauna

**Provenance: official power range; event, timing, and flexibility rules are
frozen modelling assumptions.**

Sample sauna power once:

- Uniform(6.0, 9.0) kW

Event probability:

- `WD_HOME`: 10%
- `WE_HOME`: 25%
- `AWAY`: 0%

Guest-event modifier:

- multiply probability by 1.75
- cap at 1.0

Sauna probability does not depend on daytime household occupancy.

Current behavior:

- start between 19:00 and 22:00
- duration 1-2 hours
- continuous event
- a late two-hour event may legitimately finish at midnight

Later optimization:

- service cannot be deleted
- service cannot be shortened
- preferred start may shift +/-1 hour
- absolute allowed start range: 18:00-22:30

22:30 is a latest start boundary, not a latest-completion boundary.

### Pool heating / sauna versus exact AWAY intervals

**Provenance: frozen implementation assumption.**

The existing daily activation decision remains authoritative. If pool heating
or sauna is activated on a calendar date that remains `WD_HOME` or `WE_HOME`
under the frozen 23:00 daily-classification rule, but its initially sampled
operating block overlaps an exact household `AWAY` interval:

1. Do not truncate the event.
2. Do not cancel the already-activated event.
3. Preserve its sampled duration, power, and therefore energy.
4. Resample only the event start time within that system's already-frozen
   current-behavior start range until the complete coherent event fits outside
   all exact `AWAY` intervals.

Existing start ranges remain unchanged:

- pool heating: 08:00-14:00
- sauna: 19:00-22:00

The entire event interval must be outside exact `AWAY` intervals. If no feasible
start exists anywhere inside the frozen start range for the sampled duration,
stop and report that concrete case; do not invent a fallback policy.

This rule does not change the 23:00 `AWAY_DAY` classification, exact `AWAY`
timestamps, activation probabilities, sampled duration, sampled power, energy
requirement, or any Stage 7 optimization rule.

## 10. HVAC

**Provenance: official operating-power ranges; controller, preferences, thermal
proxy, occupancy adjustments, and flexibility rules are frozen modelling
assumptions.**

Sample household operating powers once:

- heating: Uniform(1.5, 4.0) kW
- cooling: Uniform(1.0, 2.5) kW

This digital twin uses a binary rated-power `ON`/`OFF` HVAC simplification.

Sample normal comfort preferences once:

- heating preference: Uniform(20, 22) °C
- cooling preference: Uniform(23, 25) °C

Daily comfort jitter:

- Uniform(-0.5, +0.5) °C

Clamp daily jitter only for normal occupied comfort targets so they remain
within:

- heating: 20-22°C
- cooling: 23-25°C

Do not apply that occupied-band clamp to `EMPTY`/`AWAY` setbacks.

Occupancy adjustment:

- `FULL`: normal target
- `PARTIAL`: normal target
- ordinary `EMPTY`: heating target = normal - 1°C; cooling target = normal + 1°C
- `AWAY`: heating target = normal - 3°C; cooling target = normal + 3°C

### Thermal proxy

Use:

```text
T_indoor[t+1] =
T_indoor[t]
+ (T_outdoor[t] - T_indoor[t]) / 6
+ HVAC_effect[t]
```

HVAC effect:

- heating `ON`: +1°C/hour
- cooling `ON`: -1°C/hour
- `OFF`: 0

Hysteresis for cooling:

- `ON` when indoor > effective cooling target + 0.5°C
- `OFF` when indoor <= effective cooling target

Mirror logic for heating:

- `ON` when indoor < effective heating target - 0.5°C
- `OFF` when indoor >= effective heating target

Heating and cooling are mutually exclusive:

- `heat`
- `cool`
- `off`

At the first timestamp initialize:

```text
T_indoor[0] =
(effective_heating_target[0] + effective_cooling_target[0]) / 2
```

Initial HVAC mode is `off`. This deliberately starts inside the comfort band
and avoids an artificial first-hour HVAC spike. After initialization, use the
frozen recurrence and hysteresis exactly.

Outdoor temperature is the primary weather driver.

Do not require humidity, wind, or solar radiation in the HVAC controller unless
a later explicitly approved model change is made.

Warm Barcelona conditions may legitimately result in AC-dominated demand and
little or zero heating. Do not fabricate heating events.

Later optimization comfort boundaries:

- Heating: `[max(preference - 1, 20), min(preference + 1, 22)]`
- Cooling: `[max(preference - 1, 23), min(preference + 1, 25)]`

Limited pre-heating/pre-cooling may later be allowed.

Optimization may not:

- violate comfort boundaries
- eliminate HVAC service
- apply `AWAY` setbacks while the household is occupied

## 11. Cooking

**Provenance: official appliance power ranges; probabilities, timing,
composition, and consolidation rules are frozen modelling assumptions.**

Sample once:

- oven power: Uniform(2.0, 2.5) kW
- hob power: Uniform(1.5, 4.0) kW

Morning cooking:

- non-`AWAY` probability: 35%
- `AWAY`: 0%
- start: 06:30-08:30
- duration: 0.25-0.75 hours
- do not make morning cooking depend on daytime occupancy state

Evening dinner:

- non-`AWAY` probability: 80%
- `AWAY`: 0%
- start: sample uniformly between 18:00 and 21:00
- duration: 0.5-1.5 hours
- the event may cross hourly boundaries; allocate energy by actual overlap

Appliance composition per cooking event:

- hob only: 50%
- oven only: 20%
- both: 30%

Guest events increase the chance of using both oven and hob.

For a dinner that occurs during a guest event, use this frozen modelling
composition instead of the ordinary composition:

- hob only: 35%
- oven only: 15%
- both: 50%

Use one consolidated evening dinner routine. Do not create duplicate dinner
events merely because the official scenario mentions activity in both
16:00-19:00 and 19:00-23:00 blocks.

## 12. Dishwasher

**Provenance: official energy-per-cycle range; probability, timing, duration,
and flexibility rules are frozen modelling assumptions.**

Energy per cycle:

- Uniform(0.8, 1.2) kWh

Probability:

- ordinary non-`AWAY` evening: 50%
- guest event: +25 percentage points, capped at 1.0
- `AWAY`: 0%

Current start:

- 20:00-23:00

Represent as one coherent cycle:

- duration 1-2 hours
- preserve sampled total cycle energy

Later optimization:

- cycle may shift
- sampled energy must be preserved
- cycle must complete by 06:30 the following morning

## 13. Laundry

**Provenance: official washer/dryer energy ranges; all event and flexibility
rules are frozen modelling assumptions.**

Probability by daytime household occupancy:

- `FULL`: 30%
- `PARTIAL`: 20%
- `EMPTY`: 5%
- `AWAY`: 0%

Washer:

- energy: Uniform(0.6, 1.0) kWh/cycle
- duration: 1-1.5 hours

Dryer:

- follows washer with probability 70%
- energy: Uniform(1.5, 2.5) kWh/cycle
- duration: 1-1.5 hours

Current timing:

- 09:00-19:00
- coherent cycles

**Frozen modelling operationalization:** the 09:00-19:00 current-behavior
window means that required current-behavior laundry cycles must complete by
19:00. When a dryer is generated, its delay after washer completion is
Uniform(0, 30) minutes. The washer and dryer must both fit coherently so that
the generated laundry sequence completes by 19:00. Sampled cycle energies must
be preserved.

Later optimization:

- preserve sampled washer/dryer energy
- preserve washer-before-dryer ordering
- required cycles must complete by 23:00 on the same day
- optimization cannot delete required service

## 14. Electronics

**Provenance: official device power/energy ranges; probability, timing, and
event rules are frozen modelling assumptions.**

Sample household powers once:

- TV: Uniform(0.10, 0.20) kW
- computer: Uniform(0.05, 0.25) kW

Phone/tablet:

- 0.005-0.02 kWh/device/charge
- treat as minor demand
- no need to invent a separate large morning electronics event

Frozen modelling operationalization:

- model four aggregate household mobile devices
- on each non-`AWAY` day, independently give each device a 70% probability of
  one charging event
- sample each charge from 0.005-0.02 kWh/device/charge
- sample its start uniformly between 18:00 and 23:00
- assign the sampled charging energy to the selected hour
- do not use a detailed charger-power/duration model
- generate no new phone/tablet home charging events during `AWAY`

### Daytime computer use, 09:00-16:00

Probability:

- `EMPTY`: 0%
- `PARTIAL`: 35%
- `FULL`: 55%
- `AWAY`: 0%

Duration:

- 1-3 coherent hours

### Evening electronics, 19:00-23:00

- ordinary non-`AWAY`: 70%
- guest event: 85%
- `AWAY`: 0%
- duration: 1-3 coherent hours

When an evening electronics event occurs, use this frozen modelling
composition:

- TV only: 50%
- computer only: 20%
- both TV and computer: 30%

Use the household-level TV and computer powers sampled once from their frozen
official ranges. Daytime computer behavior remains unchanged and uses the
computer only.

Do not gate evening electronics using the daytime occupancy state.

## 15. Lighting

**Provenance: official lighting power range; control and allocation rules are
frozen modelling assumptions.**

Sample installed lighting power once:

- Uniform(0.10, 0.40) kW

Interior lighting:

- determine darkness from Stage 2 `shortwave_radiation`: values <= 0 are dark;
  values > 0 are not dark
- when dark, use 100% of sampled installed lighting power for `FULL`, 60% for
  `PARTIAL`, and 0% for `EMPTY` or `AWAY`
- during a guest event while occupancy permits interior activity, use 100% of
  sampled installed lighting power while dark
- when not dark, interior lighting is 0

Exterior/security lighting:

- autonomous
- when Stage 2 `shortwave_radiation` <= 0, operate at 25% of sampled lighting
  power
- when Stage 2 `shortwave_radiation` > 0, use 0
- may operate under `FULL`, `PARTIAL`, `EMPTY`, and `AWAY`

Do not treat all lighting as occupant-controlled.

## 16. Refrigerator/freezer

**Provenance: official daily-energy range; sampling and distribution rules are
frozen modelling assumptions.**

Sample daily refrigerator/freezer energy once:

- Uniform(1.5, 2.2) kWh/day

Distribute the same sampled daily energy across each 24-hour day with a fixed,
reproducible small within-day variation profile. Before normalization, variation
must remain within +/-10% around the hourly mean. Normalize the 24 hourly
weights so their daily sum is exactly the sampled refrigerator daily energy. Do
not introduce independent random hourly energy that changes the daily total.

It remains active under:

- `EMPTY`
- `PARTIAL`
- `FULL`
- `AWAY`

Do not redraw the household's refrigerator daily-energy parameter every day.

## 17. Smart-home/base infrastructure

**Provenance: official continuous-power range; sampling rule is a frozen
modelling assumption.**

Sample once:

- Uniform(0.05, 0.15) kW continuous

It is active 24/7 under all occupancy/day states.

Do not invent a large additional standby load outside the official scenario.

## 18. Guest events

**Provenance: frozen modelling assumptions.**

Probability:

- `WD_HOME`: 5%
- `WE_HOME`: 15%
- `AWAY`: 0%

Typical event window:

- 18:00-23:30

Frozen modelling operationalization:

- generate one coherent guest event
- sample its start uniformly between 18:00 and 20:30
- sample duration uniformly between 2 and 3 hours
- cap the event end at 23:30

Guest events modify existing household behavior rather than adding an arbitrary
generic guest kW load.

Guests may increase:

- cooking overlap / chance of oven + hob
- sauna probability
- electronics probability
- lighting activity
- dishwasher probability

Do not add an unexplained fixed guest electricity load.

## 19. Five behavioral blocks

**Provenance: frozen operationalization of the official residents' behavior.**

### Block 1 - 06:30-09:00

Possible:

- morning cooking
- HVAC
- overnight EV charging continuing
- pool circulation
- refrigerator/base
- lighting
- minor phone/tablet charging
- weekday household departure around 08:30-09:00 where applicable

### Block 2 - 09:00-16:00

Driven by household occupancy state.

Possible:

- HVAC
- pool/base loads
- daytime computer use
- laundry
- EV individual presence/absence
- lighting as appropriate

`AWAY` overrides normal behavior.

### Block 3 - 16:00-19:00

Activity rises.

Possible:

- weekday household returns 16:00-19:00
- weekend household returns by 19:00
- HVAC
- EV returns and possible charging
- lighting/electronics increase
- pool systems

Do not create a second duplicate dinner routine here.

### Block 4 - 19:00-23:00

Main high-demand period.

Possible:

- consolidated dinner
- evening electronics
- guest events
- sauna
- dishwasher
- EV charging
- HVAC
- lighting
- pool/base loads

Daytime occupancy must not incorrectly suppress this evening behavior.

Weekend EVs may return as late as 21:00.

### Block 5 - 23:00-06:30

Primarily:

- refrigerator/base
- HVAC
- EV charging
- possible pool operation
- security/exterior lighting

Active cooking/TV is normally absent.

A late sauna event may legitimately finish at midnight.

`AWAY` is a cross-block top-level override. Do not create `AWAY` as a sixth
behavioral block.

## 20. Stage 7 optimizer classification

**Provenance: frozen modelling assumptions for later use. No optimizer is
implemented by this document.**

### A - Fixed

- refrigerator/freezer
- smart-home/base
- security/exterior lighting when time-conditioned

### B - Behavior-driven, not optimized

- morning cooking
- dinner
- TV/computers
- phone/tablet
- interior lighting

### C - Limited flexibility

HVAC:

- comfort-constrained as specified above

Sauna:

- preserve service
- preferred start +/-1 hour
- absolute start window 18:00-22:30

Pool heating:

- preserve service if an event exists
- exact feasible shifting window deferred to Stage 7

### D - Shiftable

`EV1` / `EV2`:

- preserve required sampled charging energy
- charge only while vehicle is home
- maximum 7.4 kW
- complete before next departure

Pool circulation:

- preserve sampled daily runtime
- complete within the same calendar day

Dishwasher:

- preserve sampled cycle energy
- complete by 06:30 the next morning

Washer/dryer:

- preserve sampled energy
- preserve washer-before-dryer order
- complete by 23:00 on the same day

Important optimization principle: the optimizer may shift required service but
may not silently delete, shorten, or replace the actual service generated by the
digital twin.

Static appliance constraints and actual event instances are different concepts.
For example, Stage 7 may define dishwasher energy range = 0.8-1.2 kWh, while
Stage 3 may generate an actual dishwasher event requiring 0.93 kWh. Stage 9
must preserve that actual 0.93 kWh requirement rather than replace it with a
generic midpoint.

## 21. Tariff assumptions for later stages

**Provenance: official/common challenge assumptions. Recorded only; not
implemented here.**

- 00:00-06:00: €0.18/kWh
- 06:00-17:00: €0.28/kWh
- 17:00-22:00: €0.40/kWh
- 22:00-00:00: €0.28/kWh

PV assumptions for later stages:

- installation: €1,300/kWp
- export: €0.08/kWh
- annual O&M: 1% of initial investment

Do not implement PV economics now.

## 22. Stage 2 input contract

**Provenance: frozen project data contract.**

Stage 2 is complete and frozen.

Historical period:

- 2025-08-01 00:00 through 2025-09-30 23:00
- `Europe/Madrid`
- 61 consecutive days
- 1,464 hourly rows

Authoritative Stage 2 input:

`data/processed/stage2_barcelona_weather_solar_hourly.csv`

Columns:

- `timestamp`
- `temperature_2m`
- `relative_humidity_2m`
- `precipitation`
- `cloud_cover`
- `wind_speed_10m`
- `shortwave_radiation`
- `direct_radiation`
- `diffuse_radiation`

Stage 3 must later preserve this exact hourly timeline.

## 23. Frozen pool-heating activation rule

**Provenance: frozen modelling assumptions, not official challenge values.**

The pool-heating activation rule is resolved and frozen:

- calculate daily mean outdoor temperature from the real Stage 2 hourly
  Barcelona temperature
- below 15°C: base daily activation probability = 0.70
- 15-20°C: base daily activation probability = 0.35
- above 20°C: base daily activation probability = 0.08
- apply `FULL` x1.25, `PARTIAL` x1.00, `EMPTY`-heavy x0.60, and guest-event
  x1.30 modifiers
- set activation probability to 0 / off during `AWAY`
- cap the final activation probability at 1.0

## 24. Provenance

This document distinguishes:

- official Scenario 3 facts and ranges
- frozen modelling assumptions
- deferred/unresolved parameters

Modelling assumptions must not be presented as official challenge facts.

The official PDFs remain authoritative for official challenge facts. This
document is authoritative for the frozen modelling decisions used by the future
Stage 3 implementation. The pool-heating activation probabilities and modifiers
are frozen in Sections 8 and 23. The precise Stage 7 pool-heating shifting window
remains deferred.

