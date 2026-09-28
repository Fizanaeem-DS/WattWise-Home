"""Create the deterministic Stage 6B backend contract from frozen outputs."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .config import (
    EXPLAINED_OUTPUT,
    FIGURES_DIR,
    FROZEN_STAGE1_TO_STAGE6A_MANIFEST_SHA256,
    FROZEN_STAGE6A_MANIFEST_SHA256,
    OUTPUT_COLUMNS,
    PROBLEM_WINDOW_ORIGIN,
    PROJECT_ROOT,
    STAGE2_INPUT,
    STAGE5_PREDICTIONS,
    STAGE6A_HOURLY,
    STAGE6A_METRICS,
    SUMMARIES_OUTPUT,
)
from .explanations import ALLOWED_EXPLANATION_INPUTS, explanations, risk_label, tariff
from .figures import explained_demo


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(paths: Iterable[Path]) -> tuple[str, dict[str, str]]:
    files = sorted({path for path in paths if path.is_file() and "__pycache__" not in path.parts})
    entries = {path.relative_to(PROJECT_ROOT).as_posix(): sha256(path) for path in files}
    payload = "".join(f"{path}\t{digest}\n" for path, digest in entries.items())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), entries


def stage6a_manifest() -> tuple[str, dict[str, str]]:
    """Fingerprint every frozen Stage 6A source, output, test and report."""
    return _manifest([
        *PROJECT_ROOT.glob("data/processed/stage6a_*"),
        *PROJECT_ROOT.glob("artifacts/stage6a/**/*"),
        *PROJECT_ROOT.glob("docs/stage6a*"),
        *PROJECT_ROOT.glob("tests/test_stage6a*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage6a/**/*"),
        *PROJECT_ROOT.glob("scripts/run_stage6a.py"),
    ])


def upstream_manifest() -> tuple[str, dict[str, str]]:
    """Fingerprint the frozen Stage 1-6A surface, excluding Stage 6B itself."""
    candidates = [
        *PROJECT_ROOT.glob("data/raw/**/*"),
        *PROJECT_ROOT.glob("data/processed/*"),
        *PROJECT_ROOT.glob("models/**/*"),
        *PROJECT_ROOT.glob("artifacts/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage2/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage3a/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage3b/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage3c/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage4/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage5/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage5b/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage6a/**/*"),
        *PROJECT_ROOT.glob("scripts/run_stage[2-6]*.py"),
        *PROJECT_ROOT.glob("tests/test_stage[2-6]*.py"),
        *PROJECT_ROOT.glob("docs/STAGE1*"),
        *PROJECT_ROOT.glob("docs/stage[2-6]*"),
    ]
    return _manifest(path for path in candidates if "stage6b" not in path.as_posix().lower())


def frozen_fingerprints() -> dict[str, Any]:
    stage6a_hash, stage6a_files = stage6a_manifest()
    upstream_hash, upstream_files = upstream_manifest()
    return {
        "stage6a_manifest_sha256": stage6a_hash,
        "stage6a_file_count": len(stage6a_files),
        "stage1_to_stage6a_manifest_sha256": upstream_hash,
        "stage1_to_stage6a_file_count": len(upstream_files),
    }


def assert_frozen(fingerprints: dict[str, Any]) -> None:
    if fingerprints["stage6a_manifest_sha256"] != FROZEN_STAGE6A_MANIFEST_SHA256:
        raise RuntimeError("STOP: a frozen Stage 6A artifact changed")
    if fingerprints["stage1_to_stage6a_manifest_sha256"] != FROZEN_STAGE1_TO_STAGE6A_MANIFEST_SHA256:
        raise RuntimeError("STOP: a frozen Stage 1-6A artifact changed")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _rank_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": row["timestamp"],
        "lead_hour": row["lead_hour"],
        "point_forecast_kwh": row["point_forecast_kwh"],
        "p95_kwh": row["p95_kwh"],
        "peak_probability": row["peak_probability"],
        "peak_risk_label": row["peak_risk_label"],
        "primary_explanation": row["primary_explanation"],
        "secondary_explanation": row["secondary_explanation"],
    }


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    windows: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        windows[(row["horizon_hours"], row["forecast_origin"])].append(row)

    summaries: list[dict[str, Any]] = []
    for (horizon, origin), window in sorted(windows.items()):
        expected = sorted(
            window,
            key=lambda row: (-row["point_forecast_kwh"], -row["peak_probability"], row["timestamp"]),
        )
        risk = sorted(
            window,
            key=lambda row: (
                -row["peak_probability"],
                -row["p95_kwh"],
                -row["point_forecast_kwh"],
                row["timestamp"],
            ),
        )
        counts = Counter(row["peak_risk_label"] for row in window)
        summaries.append({
            "horizon_hours": horizon,
            "forecast_origin": origin,
            "total_expected_energy_kwh": sum(row["point_forecast_kwh"] for row in window),
            "highest_expected_demand_hour": expected[0]["timestamp"],
            "highest_expected_demand_kwh": expected[0]["point_forecast_kwh"],
            "highest_peak_risk_hour": risk[0]["timestamp"],
            "highest_peak_probability": risk[0]["peak_probability"],
            "highest_peak_risk_p95_kwh": risk[0]["p95_kwh"],
            "number_low_risk_hours": counts["LOW"],
            "number_medium_risk_hours": counts["MEDIUM"],
            "number_high_risk_hours": counts["HIGH"],
            "top_5_expected_demand_hours": [_rank_item(row) for row in expected[:5]],
            "top_5_peak_risk_hours": [_rank_item(row) for row in risk[:5]],
            "point_forecast_source": "stage5_frozen_selected_model",
            "risk_quantile_source": "stage6a_frozen_ensemble",
            "explanation_source": "stage6b_deterministic_rules",
            "provenance": "real",
        })
    return summaries


def build_rows() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    stage5_rows = _read_csv(STAGE5_PREDICTIONS)
    stage6a_rows = _read_csv(STAGE6A_HOURLY)
    weather_rows = _read_csv(STAGE2_INPUT)
    stage5 = {
        (int(row["horizon_hours"]), row["forecast_origin"], row["timestamp"], row["model"]): row
        for row in stage5_rows
    }
    weather = {row["timestamp"]: row for row in weather_rows}
    output: list[dict[str, Any]] = []

    for uncertainty in stage6a_rows:
        horizon = int(uncertainty["horizon_hours"])
        key = (
            horizon,
            uncertainty["forecast_origin"],
            uncertainty["timestamp"],
            uncertainty["stage5_selected_model"],
        )
        point_source = stage5[key]
        point = float(point_source["predicted_household_kwh"])
        if point != float(uncertainty["stage5_point_forecast_kwh"]):
            raise RuntimeError(f"STOP: Stage 5/6A point mismatch at {key}")
        timestamp = datetime.fromisoformat(uncertainty["timestamp"])
        temperature = float(weather[uncertainty["timestamp"]]["temperature_2m"])
        probability = float(uncertainty["peak_probability"])
        label = risk_label(probability)
        price, period = tariff(timestamp.hour)
        context = {
            "hour": timestamp.hour,
            "behavioral_block": uncertainty["behavioral_block"],
            "is_weekend": timestamp.weekday() >= 5,
            "temperature_2m": temperature,
            "point_forecast_kwh": point,
            "peak_probability": probability,
            "peak_risk_label": label,
            "tariff_period": period,
            "tariff_eur_per_kwh": price,
        }
        if set(context) != ALLOWED_EXPLANATION_INPUTS:
            raise RuntimeError("STOP: forbidden or missing explanation input")
        primary, secondary = explanations(context)
        output.append({
            "timestamp": uncertainty["timestamp"],
            "forecast_origin": uncertainty["forecast_origin"],
            "horizon_hours": horizon,
            "lead_hour": int(uncertainty["lead_hour"]),
            "stage5_selected_model": uncertainty["stage5_selected_model"],
            "point_forecast_kwh": point,
            "p10_kwh": float(uncertainty["ensemble_p10_kwh"]),
            "p50_kwh": float(uncertainty["ensemble_p50_kwh"]),
            "p90_kwh": float(uncertainty["ensemble_p90_kwh"]),
            "p95_kwh": float(uncertainty["ensemble_p95_kwh"]),
            "peak_threshold_kwh": float(uncertainty["peak_threshold_kwh"]),
            "peak_probability": probability,
            "peak_risk_label": label,
            "temperature_2m": temperature,
            "is_weekend": timestamp.weekday() >= 5,
            "behavioral_block": uncertainty["behavioral_block"],
            "tariff_eur_per_kwh": price,
            "tariff_period": period,
            "primary_explanation": primary,
            "secondary_explanation": secondary,
            "point_forecast_source": "stage5_frozen_selected_model",
            "risk_quantile_source": "stage6a_frozen_ensemble",
            "explanation_source": "stage6b_deterministic_rules",
            "provenance": "real",
        })
    return output, stage6a_rows


def run() -> dict[str, Any]:
    before = frozen_fingerprints()
    assert_frozen(before)
    with STAGE6A_METRICS.open(encoding="utf-8") as handle:
        metrics = json.load(handle)
    if metrics["acceptance_classification"] != "USEFUL PEAK-RISK SIGNAL":
        raise RuntimeError("STOP: frozen Stage 6A classification is not the accepted useful signal")

    rows, stage6a_rows = build_rows()
    summaries = summarize(rows)
    _write_csv(EXPLAINED_OUTPUT, rows)
    SUMMARIES_OUTPUT.write_text(
        json.dumps({
            "stage": "6B",
            "purpose": "deterministic_app_contract_transformation",
            "stage6a_classification": "USEFUL PEAK-RISK SIGNAL",
            "risk_label_thresholds_are_presentation_only": True,
            "p95_label": "high-demand potential (P95)",
            "provenance_meaning": (
                "real means generated by the project backend rather than placeholder app data; "
                "it does not mean the synthetic household is real-world measured data"
            ),
            "point_forecast_source": "stage5_frozen_selected_model",
            "risk_quantile_source": "stage6a_frozen_ensemble",
            "explanation_source": "stage6b_deterministic_rules",
            "operational_output_uses_actual_demand": False,
            "stage7_started": False,
            "stage8_started": False,
            "stage9_started": False,
            "frozen_upstream": before,
            "summary_count": len(summaries),
            "summaries": summaries,
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    demo_rows = [
        row for row in rows
        if row["horizon_hours"] == 168 and row["forecast_origin"] == PROBLEM_WINDOW_ORIGIN
    ]
    actual_by_key = {
        (int(row["horizon_hours"]), row["forecast_origin"], row["timestamp"]): float(row["actual_household_kwh"])
        for row in stage6a_rows
    }
    actual = [actual_by_key[(168, PROBLEM_WINDOW_ORIGIN, row["timestamp"])] for row in demo_rows]
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    explained_demo(FIGURES_DIR / "168h_explained_forecast_demo.svg", demo_rows, actual)

    after = frozen_fingerprints()
    assert_frozen(after)
    if after != before:
        raise RuntimeError("STOP: frozen Stage 1-6A inventory changed during Stage 6B")
    return {"row_count": len(rows), "summary_count": len(summaries), "frozen_upstream": after}


def main() -> int:
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

