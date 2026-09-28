"""Meaningful acceptance tests for the generated Stage 2 artifact."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "processed" / "stage2_barcelona_weather_solar_hourly.csv"
RAW_PATH = ROOT / "data" / "raw" / "open_meteo_era5_barcelona_2025-08-01_2025-09-30.json"
RAW_METADATA_PATH = ROOT / "data" / "raw" / "open_meteo_era5_barcelona_2025-08-01_2025-09-30_metadata.json"
VALIDATION_PATH = ROOT / "data" / "processed" / "stage2_validation_report.json"

REQUIRED_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "cloud_cover",
    "wind_speed_10m",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
]


class Stage2DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with CSV_PATH.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            cls.columns = reader.fieldnames
            cls.rows = list(reader)
        cls.timestamps = [datetime.fromisoformat(row["timestamp"]) for row in cls.rows]
        cls.raw_bytes = RAW_PATH.read_bytes()
        cls.raw = json.loads(cls.raw_bytes.decode("utf-8"))
        cls.raw_metadata = json.loads(RAW_METADATA_PATH.read_text(encoding="utf-8"))
        cls.validation = json.loads(VALIDATION_PATH.read_text(encoding="utf-8"))

    def test_required_columns_are_exactly_present(self) -> None:
        self.assertEqual(self.columns, ["timestamp", *REQUIRED_VARIABLES])

    def test_expected_start_end_and_row_count(self) -> None:
        self.assertEqual(len(self.rows), 1_464)
        self.assertEqual(self.rows[0]["timestamp"], "2025-08-01T00:00:00+02:00")
        self.assertEqual(self.rows[-1]["timestamp"], "2025-09-30T23:00:00+02:00")

    def test_timestamps_are_timezone_aware_unique_ordered_and_hourly(self) -> None:
        self.assertTrue(all(value.tzinfo is not None for value in self.timestamps))
        self.assertTrue(all(value.utcoffset() == timedelta(hours=2) for value in self.timestamps))
        self.assertEqual(len(self.timestamps), len(set(self.timestamps)))
        utc = [value.astimezone(timezone.utc) for value in self.timestamps]
        self.assertTrue(all(a < b for a, b in zip(utc, utc[1:])))
        self.assertTrue(all(b - a == timedelta(hours=1) for a, b in zip(utc, utc[1:])))

    def test_no_required_value_is_missing(self) -> None:
        for variable in REQUIRED_VARIABLES:
            self.assertTrue(all(row[variable].strip() for row in self.rows), variable)
            self.assertEqual(self.validation["missingness"][variable]["missing_count"], 0)
            self.assertEqual(
                self.validation["missingness"][variable]["coverage_percent"], 100.0
            )

    def test_physical_bounds(self) -> None:
        series = {
            name: [float(row[name]) for row in self.rows] for name in REQUIRED_VARIABLES
        }
        self.assertTrue(all(0 <= value <= 100 for value in series["relative_humidity_2m"]))
        self.assertTrue(all(value >= 0 for value in series["precipitation"]))
        self.assertTrue(all(0 <= value <= 100 for value in series["cloud_cover"]))
        self.assertTrue(all(value >= 0 for value in series["wind_speed_10m"]))
        self.assertTrue(all(-100 <= value <= 60 for value in series["temperature_2m"]))
        for name in ("shortwave_radiation", "direct_radiation", "diffuse_radiation"):
            self.assertTrue(all(value >= 0 for value in series[name]), name)

    def test_solar_coherence_and_day_night_behaviour(self) -> None:
        for row, timestamp in zip(self.rows, self.timestamps):
            ghi = float(row["shortwave_radiation"])
            direct = float(row["direct_radiation"])
            diffuse = float(row["diffuse_radiation"])
            self.assertLessEqual(abs(ghi - (direct + diffuse)), 0.2)
            if timestamp.hour <= 4:
                self.assertEqual((ghi, direct, diffuse), (0.0, 0.0, 0.0))
        dates = {timestamp.date() for timestamp in self.timestamps}
        dates_with_sun = {
            timestamp.date()
            for row, timestamp in zip(self.rows, self.timestamps)
            if float(row["shortwave_radiation"]) > 0
        }
        self.assertEqual(dates_with_sun, dates)

    def test_returned_units_and_timezone_are_preserved(self) -> None:
        self.assertEqual(self.raw["timezone"], "Europe/Madrid")
        self.assertEqual(
            self.raw["hourly_units"],
            {
                "time": "iso8601",
                "temperature_2m": "°C",
                "relative_humidity_2m": "%",
                "precipitation": "mm",
                "cloud_cover": "%",
                "wind_speed_10m": "km/h",
                "shortwave_radiation": "W/m²",
                "direct_radiation": "W/m²",
                "diffuse_radiation": "W/m²",
            },
        )

    def test_raw_payload_integrity_and_overall_validation(self) -> None:
        self.assertEqual(
            hashlib.sha256(self.raw_bytes).hexdigest(), self.raw_metadata["raw_sha256"]
        )
        self.assertEqual(len(self.raw["hourly"]["time"]), 1_464)
        self.assertEqual(self.validation["status"], "pass")
        self.assertTrue(all(self.validation["checks"].values()))


if __name__ == "__main__":
    unittest.main()
