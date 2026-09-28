# Stage 8 PV app/backend contract

## Hourly interface

```python
from hackowatt_stage8 import get_pv_generation

rows = get_pv_generation(capacity_kwp=5.0)
```

Input must be a finite numeric value greater than zero. Invalid, zero, negative, boolean, NaN, and infinite values raise `ValueError`.

The function returns 1,464 ordered dictionaries:

| Field | Type | Meaning |
|---|---:|---|
| `timestamp` | ISO-8601 string | Frozen 2025 Europe/Madrid target hour |
| `capacity_kwp` | number | Validated user-selected nominal PV capacity |
| `pv_generation_kwh` | number | Linearly scaled PV energy for that hour |

The normalized source contract is `data/processed/stage8_pv_hourly_per_kwp.csv`. Its columns are:

`timestamp, reference_capacity_kwp, pv_generation_kwh_per_kwp, pvgis_power_w_per_kwp, pvgis_sun_height_degrees, pvgis_source_year, pvgis_utc_timestamp, pvgis_local_timestamp, timezone_treatment, source`

## Annual/monthly interface

```python
from hackowatt_stage8 import get_annual_pv_summary

summary = get_annual_pv_summary(capacity_kwp=5.0)
```

The returned object contains:

- `capacity_kwp`
- `annual_generation_kwh`
- `monthly_generation_kwh`: exactly 12 `{month, generation_kwh}` objects

The normalized source contract is `data/processed/stage8_pv_monthly_per_kwp.csv`. It exposes month, 1-kWp monthly generation, monthly annual share, and the 1-kWp annual generation.

`data/processed/stage8_pv_capacity_examples.json` contains the 1-kWp reference, exact linear 3/5/8/10-kWp comparison examples, complete PVGIS provenance, and explicit false flags for optimization, economics, and battery implementation.

## Integration boundary

Stage 8 returns production only. Later stages may combine it with load to calculate self-consumption, grid import, or export. Those calculations, scheduling, economic decisions, and optimization are deliberately absent here. No comparison capacity is labeled optimal.

