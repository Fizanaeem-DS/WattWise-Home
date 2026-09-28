# Stage 6A peak-risk and uncertainty validation

## Scope and scientific limitation

Stage 6A is a retrospective validation experiment. It does not modify or
regenerate frozen Stage 1–5B artifacts, does not promote rejected Stage 5B,
does not replace the frozen Stage 5 point forecasts, and does not start Stage
6B or optimization.

**The evaluation truth is one realization from the same frozen generative
model used to form the ensemble. This is not independent validation against a
real Barcelona household.** The experiment asks whether the frozen model's
uncertainty distribution characterizes another realization generated under
the same household assumptions. It cannot establish real-world calibration.

Frozen Stage 2 weather is reused for every member. This is a
**perfect-weather-proxy retrospective evaluation**; operational weather
uncertainty is not represented.

## Ensemble construction and leakage boundary

The ensemble contains exactly 200 complete 1,464-hour trajectories. Member
`i`, zero based, uses Stage 3A seed `6100000 + 2*i` and Stage 3B seed
`6100001 + 2*i`. Thus the first seed pair is `(6100000, 6100001)` and the last
is `(6100398, 6100399)`.

Each member runs the frozen Stage 3A and Stage 3B generators against frozen
Stage 2 weather/calendar, then combines the serialized Stage 3A and Stage 3B
hourly totals exactly. No frozen Stage 3A/3B/3C file or evaluation event ledger
is supplied to ensemble generation. Future evaluation occupancy, AWAY,
guests, appliances, HVAC state, EV charging, sauna, and pool events are not
used. The Stage 3C realization is read only after ensemble generation as
evaluation truth.

The complete deterministic matrix is retained as
`data/processed/stage6a_ensemble_demand.npy`, shape `200 × 1464`, SHA-256
`d8d8487974a6f5417c33eed0a66bae0b2c2c73ee2a5b122e23818d87f8f432b2`.

Six valid members had no `AWAY_DAY` date. Frozen Stage 3B writes their hourly
outputs and ledgers, then its reporting-only metadata summary attempts
`min(empty)`. Stage 6A accepts only that exact post-generation reporting
exception after verifying the complete 1,464-hour output. No load or behavior
is altered.

## Explicit Stage 6A optional-event/AWAY policy

For pool heating and sauna only, an activated event is suppressed when the
frozen complete-event support calculation proves that no start in the frozen
range can avoid every exact AWAY interval. The activation, duration, power,
AWAY intervals, permitted range, day, and seed are retained without redraw or
substitution. The event receives no placement and exactly zero hourly energy.
Every suppression records the event type, date, duration, power, permitted
range, conflicts, member, and both seeds.

Across 200 members:

- pool heating: 19 suppressions among 1,017 activations (1.868240%);
- sauna: 2 suppressions among 1,703 activations (0.117440%);
- combined: 21 of 2,720 activated optional events (0.772059%); and
- 20 members and 21 member-date combinations were affected.

This rate is disclosed but is not judged frequent enough to materially change
the ensemble distribution. The policy is Stage 6A-only and does not authorize
changes to frozen Stage 3 artifacts.

## Distribution and peak-risk calculation

At every evaluated timestamp, Stage 6A retains ensemble mean, P05, P10, P25,
P50, P75, P90, P95, and maximum demand. Frozen Stage 5 point forecasts remain
separate.

For each frozen Stage 5 origin, the peak threshold is the 90th percentile of
Stage 3C `household_total_kwh` observed at or before that origin. Thresholds
range from 3.112946173 to 4.764862006 kWh. Peak probability is the fraction of
the 200 ensemble members at or above that threshold. Actual high-demand labels
use the same origin-specific threshold.

The forecast horizons, origins, and timestamps exactly match frozen Stage 5.
A leakage-safe simple-time comparator ranks timestamps by historical
origin-available peak frequency for their hour of day.

## Results

| Horizon | ROC AUC | Average precision | Peak prevalence | Mean risk: peak / non-peak | Top-risk peak capture | Hour-only capture |
|---:|---:|---:|---:|---:|---:|---:|
| 24h | 0.758488 | 0.258823 | 0.100000 | 0.261875 / 0.092315 | 44.285714% | 44.285714% |
| 72h | 0.845341 | 0.478751 | 0.132716 | 0.310581 / 0.081690 | 54.012346% | 44.228395% |
| 168h | 0.832293 | 0.463100 | 0.139137 | 0.319947 / 0.092502 | 43.469778% | 39.391519% |

| Horizon | Top-risk / actual-top-10% overlap | Hour-only overlap | P10–P90 coverage / width | P05–P95 coverage / width |
|---:|---:|---:|---:|---:|
| 24h | 30.000000% | 33.333333% | 85.833333% / 3.483231 kWh | 94.166667% / 4.480005 kWh |
| 72h | 51.388889% | 47.222222% | 86.882716% / 3.405258 kWh | 93.827160% / 4.428956 kWh |
| 168h | 48.529412% | 50.000000% | 87.202381% / 3.403131 kWh | 93.824405% / 4.420328 kWh |

Evening is the highest-risk behavioral block, followed by RETURN_RAMP. Across
horizons, evening mean peak probability is approximately 0.32–0.34 and return
ramp is 0.27–0.28; night is 0.02–0.03. The highest-risk hours are consistently
18:00–20:00, led by 19:00. This temporal concentration arises from the frozen
generative rules.

Calibration bins are reported without a formal real-world calibration claim.
The 24-hour upper bins and the 0.6–0.7 bins at longer horizons have small
samples. Longer-horizon bins otherwise show increasing actual peak frequency
with increasing predicted risk.

## Sep-13 168-hour diagnostic

For origin `2025-09-13T23:00:00+02:00`, the actual maximum is 17.316186 kWh
and the frozen Stage 5 maximum is 5.562286 kWh. Across timestamps, ensemble
P50, P90, and P95 maxima are 5.761302, 14.203672, and 16.158439 kWh; the
ensemble member maximum reaches 26.522969 kWh.

At the timestamp of the actual maximum, peak probability is 0.36 and P95 is
10.574839 kWh. The realized maximum is outside P05–P95 and is not in the
window's top-risk 10%. The distribution recognizes elevated risk but does not
locate or cover this exact stochastic spike.

## Decision

Stage 6A is classified **USEFUL PEAK-RISK SIGNAL**. Discrimination is
meaningful, average precision materially exceeds prevalence, top-risk capture
is far above chance and generally improves on the simple-time ranking, and
interval coverage is usable. Stage 6B must not begin automatically; it may be
considered only after independent audit accepts these results and limitations.

