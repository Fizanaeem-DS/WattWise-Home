# Stage 9 household scheduler methodology

## Scope and frozen inputs

Stage 9 consumes the frozen Stage 6B forecast display fields, the Stage 7B real production constraints, the Stage 8 PV API, and the frozen Stage 3C realization for retrospective validation only. It does not change any Stage 1-8 source or artifact. The reference demonstration uses the requested 5 kWp PV capacity; this is not a sizing recommendation.

The load classes remain authoritative:

- A, fixed: refrigerator, smart-home/base load, security/exterior lighting.
- B, behavioral and not optimized: cooking, TV/computer, phone/tablet, interior lighting.
- C, limited flexibility: HVAC, sauna, pool heating.
- D, shiftable: EV charging, pool circulation, dishwasher, washer/dryer.

All non-HVAC event energy, duration, power, identity, deadlines, dependencies, vehicle availability, exact AWAY exclusions, and approved windows come from actual Stage 3 instances through the Stage 7B production adapter. Static UI examples and midpoint values are never optimizer inputs.

## Formulation

The implementation is a deterministic mixed-integer linear program. Coherent dishwasher, washer, dryer, sauna, and pool-heating cycles choose exactly one feasible start on a 15-minute grid, with exact Stage 3 start instants included as candidates. Their hourly energy is obtained by exact interval overlap, so partial boundary hours do not alter duration, power, or energy. EV and pool-circulation services are continuous energy allocations bounded by frozen hourly availability and rated power. EVs remain vehicle-specific. Washer/dryer precedence is a hard constraint.

Current and optimized cases share one accounting engine:

`self_consumed = min(load, PV)`

`grid_import = max(load - PV, 0)`

`exported = max(PV - load, 0)`

`net_cost = tariff * grid_import - 0.08 * exported`

The frozen tariff is €0.18/kWh from 00:00-06:00, €0.28/kWh from 06:00-17:00, €0.40/kWh from 17:00-22:00, and €0.28/kWh from 22:00-24:00.

## HVAC and occupied-comfort feasibility

The frozen recurrence is applied hourly:

`T[t+1] = T[t] + (Tout[t] - T[t]) / 6 + heat[t] - cool[t]`

`heat[t]` and `cool[t]` are mutually exclusive duty fractions for within-hour ON/OFF operation at the unchanged frozen rated power and unchanged full-duty thermal effect. This does not weaken or resize the HVAC system.

The effective EMPTY/AWAY heating and cooling targets are controller targets. They constrain active preconditioning; they are not hard indoor-temperature bounds, and natural thermal drift while the equipment is off may cross them. The hard/minimum-violation rule applies only at occupied FULL or PARTIAL timestamps that are not AWAY.

Comfort is proved first by a chronological forward-reachability calculation. At every hour it propagates the complete lower/upper reachable-temperature interval under prior feasible actions, the frozen recurrence, rated effects, active controller targets, and natural off-mode drift. Each occupied bound outside that interval has an independent minimum physical violation. A binary target-limited duty-cycle MILP must jointly attain every per-hour bound; otherwise the pipeline stops. This reproduces the accepted 2025-08-10 17:00 case: the minimum violation is approximately 0.112312094 °C. No tariff, PV, or peak objective can increase any proven minimum violation.

The lexicographic sequence is:

1. minimize total unavoidable occupied comfort violation and prove each positive hour;
2. at that comfort optimum, minimize net electricity cost;
3. at cost within €0.00001 (0.001 cent) of the optimum, minimize maximum hourly household demand.

The tertiary tolerance is solely a CBC numerical-equality tolerance, not permission to trade electricity cost for peak reduction. CBC solves joint comfort attainment, the event MILP, and all objective passes with one thread, explicit non-zero solver seeds, and zero relative/absolute MIP gap. (CBC treats seed zero as clock-derived, so zero is deliberately not used.) HiGHS remains bundled for continuous diagnostic formulations but is not needed for the final proof path.

## Validation and representative week

The pipeline independently checks all service energies, coherent-cycle duration and power, availability, deadlines, washer/dryer order, AWAY exclusion, HVAC recurrence, duty limits, occupied comfort caps, accounting equality, timestamp/PV alignment, nonnegative results, operational data leakage, and the frozen Stage 1-8 manifest. A complete second solve must reproduce the identical schedule fingerprint.

The representative seven-day period is selected before looking at savings: among all rolling seven-day windows, choose the one with the most actual limited/shiftable event starts; the earliest start breaks ties. This deterministic activity rule avoids cherry-picking economic performance.

## Boundary and interpretation notes

One EV2 event begins beyond the frozen Aug-Sep horizon and is explicitly reported as `boundary_outside_window`; it has zero delivered energy in this comparison and is not silently dropped. HVAC energy may differ from current Stage 3 because the optimizer changes valid controller actions under the same frozen physics. All other satisfied services preserve actual Stage 3 energy exactly.

Operational mode consumes only Stage 6B forecast distributions, Stage 8 PV, tariff, and event requirements known at the forecast origin. It never reads future Stage 3 actual demand. The published Aug-Sep artifacts are explicitly retrospective validation outputs.
