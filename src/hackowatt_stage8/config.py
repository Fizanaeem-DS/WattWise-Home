"""Fixed Stage 8 PVGIS configuration and artifact paths."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PVGIS_API_VERSION = "5_3"
PVGIS_BASE_URL = f"https://re.jrc.ec.europa.eu/api/v{PVGIS_API_VERSION}"
PVGIS_SOURCE = "European Commission Joint Research Centre PVGIS 5.3"

LATITUDE = 41.3874
LONGITUDE = 2.1686
TIMEZONE = "Europe/Madrid"
REFERENCE_CAPACITY_KWP = 1.0
PV_TECHNOLOGY = "crystSi"
MOUNTING_PLACE = "free"
TILT_DEGREES = 30.0
ASPECT_DEGREES_PVGIS = 0.0
SYSTEM_LOSS_PERCENT = 14.0
TRACKING_TYPE = 0
USE_HORIZON = 1
HOURLY_SOURCE_YEAR = 2023
DEMO_CAPACITIES_KWP = (3.0, 5.0, 8.0, 10.0)

RAW_OUTPUT = PROJECT_ROOT / "data" / "raw" / "stage8_pvgis_raw_response.json"
STAGE2_INPUT = PROJECT_ROOT / "data" / "processed" / "stage2_barcelona_weather_solar_hourly.csv"
HOURLY_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage8_pv_hourly_per_kwp.csv"
MONTHLY_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage8_pv_monthly_per_kwp.csv"
EXAMPLES_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage8_pv_capacity_examples.json"
VALIDATION_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage8_pv_validation.json"
FIGURES_DIR = PROJECT_ROOT / "artifacts" / "stage8"

FROZEN_UPSTREAM_FILE_COUNT = 180
FROZEN_UPSTREAM_MANIFEST_SHA256 = "39cb77622eaf1216c194f78fc440a53c2bdc820b08330710d41e016e0c168065"


def pvcalc_parameters() -> dict[str, str | int | float]:
    return {
        "lat": LATITUDE,
        "lon": LONGITUDE,
        "peakpower": REFERENCE_CAPACITY_KWP,
        "loss": SYSTEM_LOSS_PERCENT,
        "angle": TILT_DEGREES,
        "aspect": ASPECT_DEGREES_PVGIS,
        "mountingplace": MOUNTING_PLACE,
        "pvtechchoice": PV_TECHNOLOGY,
        "usehorizon": USE_HORIZON,
        "outputformat": "json",
    }


def seriescalc_parameters() -> dict[str, str | int | float]:
    return {
        "lat": LATITUDE,
        "lon": LONGITUDE,
        "startyear": HOURLY_SOURCE_YEAR,
        "endyear": HOURLY_SOURCE_YEAR,
        "pvcalculation": 1,
        "peakpower": REFERENCE_CAPACITY_KWP,
        "loss": SYSTEM_LOSS_PERCENT,
        "angle": TILT_DEGREES,
        "aspect": ASPECT_DEGREES_PVGIS,
        "mountingplace": MOUNTING_PLACE,
        "pvtechchoice": PV_TECHNOLOGY,
        "trackingtype": TRACKING_TYPE,
        "usehorizon": USE_HORIZON,
        "components": 0,
        "outputformat": "json",
    }
