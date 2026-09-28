"""Fixed, auditable configuration for the Stage 2 dataset."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SOURCE_NAME = "Open-Meteo Historical Weather API"
SOURCE_API = "https://archive-api.open-meteo.com/v1/archive"
SOURCE_DOCUMENTATION = "https://open-meteo.com/en/docs/historical-weather-api"
MODEL = "era5"

# Barcelona city centre (WGS84). The API can return the centre of the selected
# ERA5 grid cell; both requested and returned coordinates are recorded.
LATITUDE = 41.3874
LONGITUDE = 2.1686
TIMEZONE = "Europe/Madrid"
START_DATE = "2025-08-01"
END_DATE = "2025-09-30"
EXPECTED_START_LOCAL = "2025-08-01T00:00:00+02:00"
EXPECTED_END_LOCAL = "2025-09-30T23:00:00+02:00"
EXPECTED_NOMINAL_ROWS = 1_464

HOURLY_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "cloud_cover",
    "wind_speed_10m",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
)

# Open-Meteo documented defaults, also checked against the returned metadata.
EXPECTED_UNITS = {
    "time": "iso8601",
    "temperature_2m": "°C",
    "relative_humidity_2m": "%",
    "precipitation": "mm",
    "cloud_cover": "%",
    "wind_speed_10m": "km/h",
    "shortwave_radiation": "W/m²",
    "direct_radiation": "W/m²",
    "diffuse_radiation": "W/m²",
}

RAW_JSON_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "open_meteo_era5_barcelona_2025-08-01_2025-09-30.json"
)
RAW_METADATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "open_meteo_era5_barcelona_2025-08-01_2025-09-30_metadata.json"
)
PROCESSED_CSV_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "stage2_barcelona_weather_solar_hourly.csv"
)
DATASET_METADATA_PATH = (
    PROJECT_ROOT / "data" / "processed" / "stage2_dataset_metadata.json"
)
VALIDATION_REPORT_PATH = (
    PROJECT_ROOT / "data" / "processed" / "stage2_validation_report.json"
)

