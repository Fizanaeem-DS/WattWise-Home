# Stage 8 rooftop-PV methodology

## Scope and source

Stage 8 produces photovoltaic generation only. It does not use demand, shift activities, optimize schedules, calculate grid imports/exports, or calculate tariffs, savings, payback, or other economics. Rejected Stage 5B outputs are not inputs.

The primary source is the European Commission Joint Research Centre **PVGIS 5.3** non-interactive API:

- `PVcalc` supplies long-term monthly and annual PV energy.
- `seriescalc` supplies the hourly PV power series.
- API documentation: <https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/api-non-interactive-service_en>
- Hourly output documentation: <https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/pvgis-5-tools/hourly-radiation_en>

Both requests and complete JSON responses are preserved in `data/raw/stage8_pvgis_raw_response.json`.

## Fixed reference configuration

The reference system is a modeling assumption for the hackathon, not an official Scenario 3 fact:

- Barcelona city-centre WGS84 coordinate frozen by Stage 2: 41.3874° N, 2.1686° E
- 1.0 kWp nominal capacity
- fixed crystalline-silicon system (`crystSi`)
- 30° tilt from horizontal
- south-facing: PVGIS aspect 0° (`+90°` west, `-90°` east)
- 14% system losses
- ventilated/free-standing mounting (`mountingplace=free`), representing conventional rack-mounted rooftop panels rather than building-integrated PV
- no tracking (`trackingtype=0`)
- PVGIS terrain horizon enabled; no user-defined roof shading
- no battery, degradation, financing, or custom inverter-clipping model

PVGIS itself accounts for the selected model’s conversion losses. Stage 8 adds no physical correction or tuning.

## Annual and monthly production

The annual and monthly values come directly from `PVcalc` and use PVGIS-SARAH3 radiation plus ERA5 meteorology over the API-reported 2005–2023 period. Annual generation is not extrapolated from the August–September project sample. The 12 rounded PVGIS monthly values sum exactly to the reported annual value for this response.

## Hourly profile and timezone alignment

The hourly source is the latest complete year accepted by the API, 2023, using PVGIS-SARAH3. This is a historical reference shape, not a claim to reproduce 2025 weather.

PVGIS `seriescalc` timestamps are UTC and its SARAH3 records for Barcelona occur at `HH:10`. Processing performs these deterministic steps:

1. Parse each source timestamp as UTC.
2. Convert it with the IANA `Europe/Madrid` timezone.
3. Assign the record to the containing local clock hour; for example, `22:10 UTC` becomes `00:10 CEST` and maps to local hour `00:00`.
4. Match the source calendar month/day/hour to the frozen 2025 Stage 2 timestamp.

Only August and September are selected, so every target is in CEST (`UTC+02:00`) and the October daylight-saving fallback ambiguity is outside the output interval. The result exactly matches the 1,464 frozen timestamps from `2025-08-01T00:00:00+02:00` through `2025-09-30T23:00:00+02:00`.

PVGIS reports hourly `P` in watts. For a one-hour interval and a 1-kWp reference system, Stage 8 records `P / 1000` as kWh per hour per kWp. Source UTC/local timestamps, power, sun height, and conversion wording remain in every processed row.

## Capacity scaling

For any finite capacity greater than zero:

`generation(capacity) = generation_per_1_kwp × capacity_kwp`

No capacity is selected as optimal. The 3, 5, 8, and 10-kWp outputs are comparison examples only.

## Stage 2 solar sanity check

Stage 2 shortwave radiation is never used to create or tune PV generation. It is joined only after PVGIS processing for a descriptive sanity check. The validation artifact reports all-hour and daylight-only correlations and the number of clock-hour differences around dawn/dusk. Perfect agreement is neither expected nor required because the datasets use different years, radiation products, planes, and electrical conversion models.

