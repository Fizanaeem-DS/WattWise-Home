# Stage 4 digital-twin validation gate

## Scope

Stage 4 is a read-only validation gate for the frozen Stage 3C historical
profile. It computes physical, behavioral, statistical, peak, occupancy, and
simple-baseline evidence without regenerating, tuning, scaling, filtering, or
otherwise changing the twin. It does not train a machine-learning model and
does not start Stage 5.

The source profile is fingerprinted with SHA-256 in every Stage 4 JSON output.
The acceptance suite also pins that frozen fingerprint and confirms the profile
is unchanged.

## Input integrity and physical rules

The gate requires 1,464 unique consecutive hourly observations covering 61
complete calendar days with the frozen Europe/Madrid summer offset. It checks
non-negativity and category reconciliation, then validates the frozen maximum
rates for each EV, HVAC heating/cooling, sauna, pool heating, and circulation.
It also checks heating/cooling exclusion, EV home state, and applicable AWAY
suppression. Exterior/security lighting is intentionally not treated as an
AWAY-suppressed active routine load because the frozen Stage 3A specification
keeps it available as a security service.

No external universal residential-energy threshold is introduced. Energy mix
is interpreted qualitatively against the official large detached smart-home
scenario, with all lower-level component totals retained for traceability.

## Descriptive definitions

All reported standard deviations are population standard deviations. Percentile
values use linear interpolation at rank `(n - 1) * p`. The top 5% contains
`ceil(0.05 * 1464) = 74` observations, sorted by descending actual demand with
timestamp as a deterministic tie-break.

The reproducible analytical blocks are:

- `NIGHT`: 23:00 and 00:00-06:00
- `MORNING`: 07:00-08:00
- `DAYTIME`: 09:00-15:00
- `RETURN_RAMP`: 16:00-18:00
- `EVENING`: 19:00-22:00

These bins are analysis views only and do not alter any frozen event timing.

## Variability analysis

Daily totals and each hour-of-day are summarized by mean, population standard
deviation, and coefficient of variation. Exact 24-value profiles are compared
as serialized in the frozen dataset to count unique days and pairwise identical
profiles. Daily variability is also decomposed across the six frozen categories
to show whether changes track modeled mechanisms rather than added noise.

## Chronological simple baselines

Training is 1-31 August 2025 (744 hours); evaluation is 1-30 September 2025
(720 hours). There is no random split.

- `B1`: actual value exactly 24 hours earlier
- `B2`: actual value exactly 168 hours earlier
- `B3`: August-only mean for each of the 168 Monday-hour through Sunday-hour
  slots, frozen before evaluating September

Each baseline reports MAE, RMSE, and WAPE. Peak retention selects the top 10%
of actual evaluation observations and the same number of highest predictions,
then reports timestamp-set overlap. Deterministic timestamp tie-breaking is
used for both sets.

## Classification

No invented universal error cutoff is used. The final classification combines:

- hard input-integrity and frozen physical-rule checks
- exact repeated-profile evidence
- daily and hour-of-day variability
- the magnitude of all three simple-baseline errors
- incomplete or near-perfect peak retention
- traceability of peaks to frozen high-power components
- consistency of block and occupancy evidence with the scenario narrative

A failed hard integrity or physical rule produces `FAIL`. Otherwise, the report
states the observed evidence and its qualitative conclusion. This run is
classified `PASS`: every hard check passes, all 61 daily profiles are unique,
daily CV is substantial, baseline errors are large relative to mean load, peak
retention is incomplete, and peaks are concentrated in return/evening periods
with traceable EV/HVAC/sauna/pool/cooking contributions.

## Outputs

- `data/processed/stage4_validation_metrics.json`
- `data/processed/stage4_baseline_metrics.json`
- `data/processed/stage4_validation_report.json`
- ten dependency-free SVG figures under `artifacts/stage4_validation/`

The SVGs are validation artifacts only. A Stage 4 `PASS` means the frozen twin
is suitable to proceed to forecasting analysis; it is not proof of real-world
accuracy or performance beyond the 61-day observation window.
