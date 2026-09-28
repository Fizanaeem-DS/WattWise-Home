"""Read-only adapters for frozen Stage 8 and Stage 9 inputs."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import sys
import types
from typing import Any

from hackowatt_stage8 import get_annual_pv_summary, get_pv_generation

from .config import STAGE8_EXAMPLES, STAGE8_HOURLY, STAGE9_HOURLY, STAGE9_SUMMARY


def _load_frozen_stage9_module(name: str):
    """Load one frozen Stage 9 module without running its optimizer initializer."""

    package_name = "_hackowatt_stage10_frozen_stage9"
    source_dir = Path(__file__).resolve().parent.parent / "hackowatt_stage9"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(source_dir)]
        sys.modules[package_name] = package
    qualified = f"{package_name}.{name}"
    if qualified in sys.modules:
        return sys.modules[qualified]
    spec = importlib.util.spec_from_file_location(qualified, source_dir / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load frozen Stage 9 {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
    return module


_load_frozen_stage9_module("config")
_stage9_accounting = _load_frozen_stage9_module("accounting")
_stage9_data = _load_frozen_stage9_module("data")
account_hour = _stage9_accounting.account_hour
tariff_eur_per_kwh = _stage9_data.tariff_eur_per_kwh


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def authoritative_inputs() -> dict[str, Any]:
    hourly = read_csv(STAGE9_HOURLY)
    stage8 = read_json(STAGE8_EXAMPLES)
    return {
        "stage8_hourly_rows": len(read_csv(STAGE8_HOURLY)),
        "stage8_annual_generation_kwh_per_kwp": stage8["reference_system"]["annual_generation_kwh_per_kwp"],
        "stage9_hourly_rows": len(hourly),
        "timestamp_start": hourly[0]["timestamp"],
        "timestamp_end": hourly[-1]["timestamp"],
        "timezone": "Europe/Madrid (+02:00 throughout Aug-Sep 2025)",
        "load_unit": "kWh per one-hour interval",
        "pv_unit": "kWh per one-hour interval",
        "currency": "EUR",
        "stage9_summary": read_json(STAGE9_SUMMARY),
    }


__all__ = [
    "account_hour", "authoritative_inputs", "get_annual_pv_summary",
    "get_pv_generation", "read_csv", "read_json", "tariff_eur_per_kwh",
]
