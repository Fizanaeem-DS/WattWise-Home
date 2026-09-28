# Stage 6B explanation methodology

## Scope

Stage 6B is a deterministic presentation transformation. It does not train a model, alter a forecast, rerun an ensemble, or create a new uncertainty calculation. Expected demand is copied from the frozen Stage 5 selected model. P10, P50, P90, P95, the origin-specific peak threshold, and peak probability are copied from the frozen Stage 6A ensemble output. Rejected Stage 5B results are not used.

Risk labels are display categories only:

- `LOW`: probability below 0.20
- `MEDIUM`: probability from 0.20 inclusive to 0.40 exclusive
- `HIGH`: probability at or above 0.40

These cutoffs are not statistically calibrated decision boundaries. The continuous probability is always retained.

## Explanation inputs and privacy boundary

The explanation function accepts exactly the forecast hour, frozen behavioral time block, weekend flag, frozen Stage 2 outdoor temperature, Stage 5 expected demand, Stage 6A probability, its display label, and tariff context. It never receives actual future demand, an event ledger, occupancy, EV, sauna, guest, pool-heating, indoor-temperature, or realized HVAC state.

Every explanation is deterministic, short, and probabilistic. It describes what *can* contribute under the frozen household rules. It does not claim that a hidden event will occur.

## Rule priority

At most one primary and one secondary explanation are returned, in this fixed priority order:

1. Elevated evening overlap: 16:00–22:59 with probability at least 0.20. The stronger wording applies at 18:00–20:59 with probability at least 0.40.
2. Warm-weather cooling context: outdoor temperature at least 25.5 °C. This is not a new fitted threshold; the frozen normal cooling target is capped at 25 °C and the frozen controller starts cooling above target plus 0.5 °C. Outdoor temperature is only a context proxy and does not reveal a future indoor or HVAC state.
3. Pool-system possibility: 06:00–22:59, the union of the frozen circulation and heating operating support.
4. Weekend daytime activity: weekend hours from 07:00–18:59.
5. Highest-price tariff context: 17:00–21:59.
6. Low-risk overnight context: 23:00–06:59 with probability below 0.20.

If none applies, a neutral frozen-pattern explanation is used. Candidate rules are evaluated in the order above and only the first two are emitted.

## Rankings and summaries

Each of the 27 evaluated windows is summarized independently.

- Highest expected demand sorts by descending frozen Stage 5 point forecast, then descending peak probability, then earlier timestamp.
- Highest peak risk sorts by descending Stage 6A probability, descending P95, descending Stage 5 point forecast, then earlier timestamp.
- Total expected energy is the sum of Stage 5 point forecasts, never the ensemble P50.

P95 is labeled **high-demand potential (P95)**. It is an ensemble percentile, not a physical maximum.

## Tariffs

The frozen challenge tariff mapping is applied by local clock hour: €0.18/kWh from 00:00–05:59, €0.28/kWh from 06:00–16:59, €0.40/kWh from 17:00–21:59, and €0.28/kWh from 22:00–23:59.

## Demo boundary

The Sep-13 168-hour SVG includes actual demand only as explicitly labeled retrospective evaluation truth. Actual demand is absent from the operational CSV and summary contract and is not an explanation input.

