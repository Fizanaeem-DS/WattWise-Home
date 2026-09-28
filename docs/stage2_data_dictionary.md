# Stage 2 data dictionary and methodology

## Acquisition

- Source: Open-Meteo Historical Weather API (`/v1/archive`)
- Model: ERA5, explicitly selected for a reproducible reanalysis source
- Requested coordinate: 41.3874° N, 2.1686° E (Barcelona city centre, WGS84)
- Timezone: `Europe/Madrid`, explicitly requested
- Period: 2025-08-01 through 2025-09-30, inclusive
- Resolution: hourly
- Open-Meteo documentation:
  https://open-meteo.com/en/docs/historical-weather-api

Open-Meteo can return the centre of its selected model grid cell rather than the
exact requested point. Both coordinate pairs and the returned elevation are
recorded in the raw acquisition metadata.

## Variables

Definitions below follow Open-Meteo's Historical Weather API documentation.

| Column | Valid time | Returned unit | Definition |
|---|---|---:|---|
| `timestamp` | Hour label | ISO 8601 with UTC offset | Raw local time assigned `Europe/Madrid` and serialized with its explicit offset. |
| `temperature_2m` | Instant | °C | Air temperature at 2 metres above ground. |
| `relative_humidity_2m` | Instant | % | Relative humidity at 2 metres above ground. |
| `precipitation` | Preceding-hour sum | mm | Total precipitation: rain, showers, and snow. |
| `cloud_cover` | Instant | % | Total cloud cover as an area fraction. |
| `wind_speed_10m` | Instant | km/h | Wind speed at 10 metres above ground. |
| `shortwave_radiation` | Preceding-hour mean | W/m² | Global horizontal irradiance (GHI). |
| `direct_radiation` | Preceding-hour mean | W/m² | Direct solar radiation on the horizontal plane. |
| `diffuse_radiation` | Preceding-hour mean | W/m² | Diffuse solar radiation on the horizontal plane (DHI). |

Open-Meteo defines horizontal GHI as direct radiation plus diffuse radiation.
The pipeline checks that identity only within a 0.2 W/m² tolerance for response
rounding. It does not confuse horizontal direct radiation with direct normal
irradiance.

## Processing

The raw JSON is saved byte-for-byte before processing. Weather and solar values
are neither converted nor imputed. The only representation change is timestamp
handling: Open-Meteo's local wall-clock strings are assigned the explicitly
requested `Europe/Madrid` zone and written with a UTC offset. CSV was chosen
because it is transparent, diffable, dependency-free, and directly loadable by
Python's standard library or pandas.

## Validation design

- Exact start/end, row count, ordering, uniqueness, missing hours, and one-hour
  UTC continuity are checked.
- Missing count and coverage percentage are reported for every variable.
- Humidity and cloud cover must be in 0-100%; precipitation, wind, and solar
  values must be non-negative.
- Temperature uses only broad physical corruption limits (-100 to 60 °C), not a
  narrow Barcelona climatology filter.
- Nighttime solar uses a conservative local 00:00-04:00 window. This is fully
  dark in Barcelona in August and September and respects the fact that each
  radiation observation is the preceding-hour mean.
- Every date must contain positive shortwave radiation.

