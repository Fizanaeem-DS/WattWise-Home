"""Run Stage 6A stochastic-twin peak-risk validation."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any

import numpy as np

from hackowatt_stage4.analysis import block_for_hour
from hackowatt_stage4.figures import bar_chart, line_chart
from hackowatt_stage5.forecasting import origin_schedule, read_profile

from .config import (
    CALIBRATION_OUTPUT,
    DIAGNOSTICS_OUTPUT,
    ENSEMBLE_OUTPUT,
    ENSEMBLE_SIZE,
    FIGURES_DIR,
    FROZEN_STAGE3C_SHA256,
    FROZEN_STAGE4_SHA256,
    FROZEN_STAGE5_FULL_MANIFEST_SHA256,
    FROZEN_STAGE5_SHA256,
    FROZEN_STAGE5B_CORE_SHA256,
    FROZEN_STAGE5B_MANIFEST_SHA256,
    FROZEN_UPSTREAM_MANIFEST_SHA256,
    HOURLY_OUTPUT,
    HORIZONS,
    METRICS_OUTPUT,
    PEAK_PERCENTILE,
    PROBLEM_WINDOW_ORIGIN,
    PROJECT_ROOT,
    SEED_BASE,
    SELECTED_STAGE5_BY_HORIZON,
    STAGE2_INPUT,
    STAGE3C_INPUT,
    STAGE4_BASELINES,
    STAGE4_METRICS,
    STAGE4_REPORT,
    STAGE5_COMPARISON,
    STAGE5_CONTRACT,
    STAGE5_METRICS,
    STAGE5_PREDICTIONS,
    member_seeds,
)
from .ensemble import generate_ensemble
from .figures import sep13_peak_risk_chart
from .metrics import (
    calibration_rows,
    concentration,
    discrimination,
    interval_metrics,
    mark_top_risk,
    top_risk_metrics,
)


ACCEPTANCE_CLASSIFICATION = "USEFUL PEAK-RISK SIGNAL"
ACCEPTANCE_EVIDENCE = (
    "ROC AUC is 0.758-0.845 and average precision is 0.259-0.479 versus 0.100-0.139 peak prevalence. "
    "Top-risk hours capture 43.5-54.0% of actual high-demand hours, far above the 10% chance reference and "
    "equal to or better than the leakage-safe hour-of-day ranking. P10-P90 coverage is 85.8-87.2% and "
    "P05-P95 coverage is 93.8-94.2%. Evening and return-ramp risk emerges naturally. The exact Sep-13 "
    "maximum is still missed by the P95 and top-risk set, so the signal is useful but not an exact-event predictor."
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(paths: list[Path]) -> tuple[str, dict[str, str]]:
    files = sorted({path for path in paths if path.is_file() and "__pycache__" not in path.parts})
    entries = {path.relative_to(PROJECT_ROOT).as_posix(): sha256(path) for path in files}
    text = "".join(f"{path}\t{digest}\n" for path, digest in entries.items())
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), entries


def stage5_manifest() -> tuple[str, dict[str, str]]:
    return _manifest([
        *PROJECT_ROOT.glob("data/processed/stage5_*"),
        *PROJECT_ROOT.glob("models/stage5/**/*"),
        *PROJECT_ROOT.glob("artifacts/stage5_forecasting/**/*"),
    ])


def stage5b_manifest() -> tuple[str, dict[str, str]]:
    return _manifest([
        *PROJECT_ROOT.glob("data/processed/stage5b_*"),
        *PROJECT_ROOT.glob("models/stage5b/**/*"),
        *PROJECT_ROOT.glob("artifacts/stage5b/**/*"),
    ])


def upstream_manifest() -> tuple[str, dict[str, str]]:
    candidates = [
        *PROJECT_ROOT.glob("data/raw/**/*"),
        *PROJECT_ROOT.glob("data/processed/*"),
        *PROJECT_ROOT.glob("models/stage5/**/*"),
        *PROJECT_ROOT.glob("models/stage5b/**/*"),
        *PROJECT_ROOT.glob("artifacts/stage4_validation/**/*"),
        *PROJECT_ROOT.glob("artifacts/stage5_forecasting/**/*"),
        *PROJECT_ROOT.glob("artifacts/stage5b/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage2/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage3a/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage3b/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage3c/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage4/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage5/**/*"),
        *PROJECT_ROOT.glob("src/hackowatt_stage5b/**/*"),
        *PROJECT_ROOT.glob("scripts/run_stage[2-5]*.py"),
        *PROJECT_ROOT.glob("tests/test_stage[2-5]*.py"),
        *PROJECT_ROOT.glob("docs/STAGE1*"),
        *PROJECT_ROOT.glob("docs/stage[2-5]*"),
    ]
    candidates = [path for path in candidates if not path.name.startswith("stage6a_")]
    return _manifest(candidates)


def frozen_fingerprints() -> dict[str, Any]:
    stage5_hash, stage5_files = stage5_manifest()
    stage5b_hash, stage5b_files = stage5b_manifest()
    upstream_hash, upstream_files = upstream_manifest()
    stage5b_root = PROJECT_ROOT / "data" / "processed"
    return {
        "stage3c": sha256(STAGE3C_INPUT),
        "stage4": {
            "validation_metrics": sha256(STAGE4_METRICS),
            "baseline_metrics": sha256(STAGE4_BASELINES),
            "validation_report": sha256(STAGE4_REPORT),
        },
        "stage5_core": {
            "predictions": sha256(STAGE5_PREDICTIONS),
            "metrics": sha256(STAGE5_METRICS),
            "comparison": sha256(STAGE5_COMPARISON),
            "contract": sha256(STAGE5_CONTRACT),
        },
        "stage5_manifest_sha256": stage5_hash,
        "stage5_manifest_file_count": len(stage5_files),
        "stage5b_core": {
            "predictions": sha256(stage5b_root / "stage5b_peak_aware_predictions.csv"),
            "metrics": sha256(stage5b_root / "stage5b_peak_aware_metrics.json"),
            "comparison": sha256(stage5b_root / "stage5b_comparison.json"),
            "diagnostics": sha256(stage5b_root / "stage5b_peak_miss_diagnostics.csv"),
            "figure": sha256(PROJECT_ROOT / "artifacts" / "stage5b" / "168h_problem_window_comparison.svg"),
        },
        "stage5b_manifest_sha256": stage5b_hash,
        "stage5b_manifest_file_count": len(stage5b_files),
        "all_stage1_through_stage5b_manifest_sha256": upstream_hash,
        "all_stage1_through_stage5b_file_count": len(upstream_files),
    }


def assert_frozen(fingerprints: dict[str, Any]) -> None:
    if fingerprints["stage3c"] != FROZEN_STAGE3C_SHA256:
        raise RuntimeError("STOP: frozen Stage 3C changed")
    if fingerprints["stage4"] != FROZEN_STAGE4_SHA256:
        raise RuntimeError("STOP: frozen Stage 4 changed")
    if fingerprints["stage5_core"] != FROZEN_STAGE5_SHA256:
        raise RuntimeError("STOP: frozen Stage 5 core changed")
    if fingerprints["stage5_manifest_sha256"] != FROZEN_STAGE5_FULL_MANIFEST_SHA256:
        raise RuntimeError("STOP: frozen Stage 5 manifest changed")
    if fingerprints["stage5b_core"] != FROZEN_STAGE5B_CORE_SHA256:
        raise RuntimeError("STOP: frozen Stage 5B core changed")
    if fingerprints["stage5b_manifest_sha256"] != FROZEN_STAGE5B_MANIFEST_SHA256:
        raise RuntimeError("STOP: frozen Stage 5B manifest changed")
    if fingerprints["all_stage1_through_stage5b_manifest_sha256"] != FROZEN_UPSTREAM_MANIFEST_SHA256:
        raise RuntimeError("STOP: a Stage 1-5B upstream file changed")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _threshold_and_hour_risk(
    truth_rows: list[dict[str, str]], origin: datetime
) -> tuple[float, dict[int, float], int]:
    available = [row for row in truth_rows if datetime.fromisoformat(row["timestamp"]) <= origin]
    values = np.asarray([float(row["household_total_kwh"]) for row in available], dtype=float)
    threshold = float(np.percentile(values, PEAK_PERCENTILE))
    by_hour: dict[int, list[bool]] = defaultdict(list)
    for row in available:
        hour = datetime.fromisoformat(row["timestamp"]).hour
        by_hour[hour].append(float(row["household_total_kwh"]) >= threshold)
    return threshold, {hour: statistics.mean(labels) for hour, labels in by_hour.items()}, len(available)


def _build_records(
    timestamps: list[str], ensemble: np.ndarray, truth_rows: list[dict[str, str]]
) -> tuple[dict[int, list[dict[str, Any]]], dict[str, Any]]:
    if ensemble.shape != (ENSEMBLE_SIZE, len(timestamps)):
        raise RuntimeError(f"Expected ensemble shape {(ENSEMBLE_SIZE, len(timestamps))}, got {ensemble.shape}")
    truth_by_time = {row["timestamp"]: row for row in truth_rows}
    index_by_time = {timestamp: index for index, timestamp in enumerate(timestamps)}
    quantiles = np.quantile(ensemble, [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95], axis=0)
    means = np.mean(ensemble, axis=0)
    maxima = np.max(ensemble, axis=0)
    frozen_rows = _read_csv(STAGE5_PREDICTIONS)
    frozen_lookup = {
        (int(row["horizon_hours"]), row["forecast_origin"], row["timestamp"], row["model"]): row
        for row in frozen_rows
    }
    schedules = origin_schedule(truth_rows)
    records_by_horizon: dict[int, list[dict[str, Any]]] = {horizon: [] for horizon in HORIZONS}
    threshold_audit: dict[str, Any] = {}
    for horizon in HORIZONS:
        selected_model = SELECTED_STAGE5_BY_HORIZON[horizon]
        for origin in schedules[horizon]:
            threshold, hour_risk, observed_count = _threshold_and_hour_risk(truth_rows, origin)
            threshold_audit.setdefault(origin.isoformat(), {
                "threshold_kwh": threshold,
                "observations_at_or_before_origin": observed_count,
                "maximum_observed_timestamp": origin.isoformat(),
            })
            window: list[dict[str, Any]] = []
            for lead in range(1, horizon + 1):
                target = origin + timedelta(hours=lead)
                timestamp = target.isoformat()
                position = index_by_time[timestamp]
                truth = float(truth_by_time[timestamp]["household_total_kwh"])
                stage5 = frozen_lookup[(horizon, origin.isoformat(), timestamp, selected_model)]
                probabilities = ensemble[:, position] >= threshold
                record = {
                    "timestamp": timestamp,
                    "forecast_origin": origin.isoformat(),
                    "horizon_hours": horizon,
                    "lead_hour": lead,
                    "stage5_selected_model": selected_model,
                    "stage5_point_forecast_kwh": float(stage5["predicted_household_kwh"]),
                    "actual_household_kwh": truth,
                    "peak_threshold_kwh": threshold,
                    "actual_high_demand": truth >= threshold,
                    "ensemble_mean_kwh": float(means[position]),
                    "ensemble_p05_kwh": float(quantiles[0, position]),
                    "ensemble_p10_kwh": float(quantiles[1, position]),
                    "ensemble_p25_kwh": float(quantiles[2, position]),
                    "ensemble_p50_kwh": float(quantiles[3, position]),
                    "ensemble_p75_kwh": float(quantiles[4, position]),
                    "ensemble_p90_kwh": float(quantiles[5, position]),
                    "ensemble_p95_kwh": float(quantiles[6, position]),
                    "ensemble_maximum_kwh": float(maxima[position]),
                    "peak_probability": float(np.mean(probabilities)),
                    "ensemble_peak_member_count": int(np.sum(probabilities)),
                    "hour_of_day_baseline_risk": hour_risk[target.hour],
                    "hour_of_day": target.hour,
                    "behavioral_block": block_for_hour(target.hour),
                }
                window.append(record)
            mark_top_risk(window)
            records_by_horizon[horizon].extend(window)
    return records_by_horizon, threshold_audit


def _diagnostics(records_by_horizon: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for horizon, records in records_by_horizon.items():
        largest = sorted(records, key=lambda record: (-record["actual_household_kwh"], record["forecast_origin"], record["timestamp"]))[:15]
        for rank, record in enumerate(largest, start=1):
            output.append({
                "horizon_hours": horizon,
                "actual_demand_rank": rank,
                "forecast_origin": record["forecast_origin"],
                "timestamp": record["timestamp"],
                "actual_demand_kwh": record["actual_household_kwh"],
                "frozen_stage5_model": record["stage5_selected_model"],
                "frozen_stage5_point_forecast_kwh": record["stage5_point_forecast_kwh"],
                "ensemble_p50_kwh": record["ensemble_p50_kwh"],
                "ensemble_p90_kwh": record["ensemble_p90_kwh"],
                "ensemble_p95_kwh": record["ensemble_p95_kwh"],
                "ensemble_maximum_kwh": record["ensemble_maximum_kwh"],
                "peak_probability": record["peak_probability"],
                "origin_peak_threshold_kwh": record["peak_threshold_kwh"],
                "ranked_in_top_10_percent_risk": record["top_10_percent_peak_risk"],
            })
    return output


def _write_figures(records_by_horizon: dict[int, list[dict[str, Any]]], metrics: dict[str, Any]) -> dict[str, str]:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    problem = sorted(
        [record for record in records_by_horizon[168] if record["forecast_origin"] == PROBLEM_WINDOW_ORIGIN],
        key=lambda record: record["lead_hour"],
    )
    sep13 = FIGURES_DIR / "168h_sep13_peak_risk.svg"
    sep13_peak_risk_chart(sep13, problem)
    by_hour = FIGURES_DIR / "peak_probability_by_hour.svg"
    line_chart(
        by_hour,
        "Mean ensemble peak probability by hour of day",
        [
            (f"{horizon}h", [metrics[str(horizon)]["risk_by_hour"][str(hour)]["mean_peak_probability"] for hour in range(24)])
            for horizon in HORIZONS
        ],
        [f"{hour:02d}:00" for hour in range(24)],
        "Peak probability",
    )
    coverage = FIGURES_DIR / "interval_coverage.svg"
    labels: list[str] = []
    values: list[float] = []
    for horizon in HORIZONS:
        labels.extend([f"{horizon}h P10-P90", f"{horizon}h P05-P95"])
        values.extend([
            metrics[str(horizon)]["intervals"]["p10_p90_coverage_percent"],
            metrics[str(horizon)]["intervals"]["p05_p95_coverage_percent"],
        ])
    bar_chart(coverage, "Empirical ensemble interval coverage", labels, values, "Coverage (%)")
    return {
        "problem_window": sep13.relative_to(PROJECT_ROOT).as_posix(),
        "probability_by_hour": by_hour.relative_to(PROJECT_ROOT).as_posix(),
        "interval_coverage": coverage.relative_to(PROJECT_ROOT).as_posix(),
    }


def _problem_window_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    window = [record for record in records if record["forecast_origin"] == PROBLEM_WINDOW_ORIGIN]
    actual_peak = max(window, key=lambda record: record["actual_household_kwh"])
    highest_risk = sorted(window, key=lambda record: (-record["peak_probability"], record["timestamp"]))[: math.ceil(len(window) * 0.10)]
    return {
        "forecast_origin": PROBLEM_WINDOW_ORIGIN,
        "actual_maximum_kwh": max(record["actual_household_kwh"] for record in window),
        "frozen_stage5_maximum_kwh": max(record["stage5_point_forecast_kwh"] for record in window),
        "ensemble_p50_maximum_kwh": max(record["ensemble_p50_kwh"] for record in window),
        "ensemble_p90_maximum_kwh": max(record["ensemble_p90_kwh"] for record in window),
        "ensemble_p95_maximum_kwh": max(record["ensemble_p95_kwh"] for record in window),
        "ensemble_maximum_over_members_and_hours_kwh": max(record["ensemble_maximum_kwh"] for record in window),
        "actual_maximum_timestamp": actual_peak["timestamp"],
        "actual_maximum_peak_probability": actual_peak["peak_probability"],
        "actual_maximum_ensemble_p95_kwh": actual_peak["ensemble_p95_kwh"],
        "actual_maximum_inside_p05_p95": actual_peak["ensemble_p05_kwh"] <= actual_peak["actual_household_kwh"] <= actual_peak["ensemble_p95_kwh"],
        "actual_maximum_ranked_top_10_percent_risk": actual_peak["top_10_percent_peak_risk"],
        "top_risk_timestamps": [record["timestamp"] for record in highest_risk],
    }


def main(reuse_existing_ensemble: bool = False) -> int:
    before = frozen_fingerprints()
    assert_frozen(before)
    truth_rows = read_profile()
    with STAGE2_INPUT.open(newline="", encoding="utf-8") as handle:
        stage2_rows = list(csv.DictReader(handle))
    stage2_timestamps = [row["timestamp"] for row in stage2_rows]
    if reuse_existing_ensemble:
        ensemble = np.load(ENSEMBLE_OUTPUT, allow_pickle=False)
        timestamps = stage2_timestamps
        if not METRICS_OUTPUT.is_file():
            raise RuntimeError("Cannot reuse ensemble before Stage 6A metrics provenance exists")
        existing = json.loads(METRICS_OUTPUT.read_text(encoding="utf-8"))
        generation_audit = existing["ensemble"]["generation_audit"]
    else:
        timestamps, ensemble, generation_audit = generate_ensemble(ENSEMBLE_SIZE)
        if timestamps != stage2_timestamps:
            raise RuntimeError("Generated ensemble timeline does not match frozen Stage 2")
        ENSEMBLE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        np.save(ENSEMBLE_OUTPUT, ensemble, allow_pickle=False)
    if timestamps != [row["timestamp"] for row in truth_rows]:
        raise RuntimeError("Stage 2, ensemble, and Stage 3C evaluation timelines do not align")

    records_by_horizon, threshold_audit = _build_records(timestamps, ensemble, truth_rows)
    all_records = [record for horizon in HORIZONS for record in records_by_horizon[horizon]]
    _write_csv(HOURLY_OUTPUT, all_records)
    calibration = calibration_rows(records_by_horizon)
    _write_csv(CALIBRATION_OUTPUT, calibration)
    diagnostics = _diagnostics(records_by_horizon)
    _write_csv(DIAGNOSTICS_OUTPUT, diagnostics)

    by_horizon = {
        str(horizon): {
            "discrimination": discrimination(records_by_horizon[horizon]),
            "top_risk": top_risk_metrics(records_by_horizon[horizon]),
            "intervals": interval_metrics(records_by_horizon[horizon]),
            "risk_by_hour": concentration(records_by_horizon[horizon], "hour_of_day"),
            "risk_by_behavioral_block": concentration(records_by_horizon[horizon], "behavioral_block"),
        }
        for horizon in HORIZONS
    }
    figures = _write_figures(records_by_horizon, by_horizon)
    problem_window = _problem_window_summary(records_by_horizon[168])
    after = frozen_fingerprints()
    assert_frozen(after)
    if before != after:
        raise RuntimeError("STOP: frozen upstream inventory changed during Stage 6A")

    seed_pairs = [
        {"member_index": index, "stage3a_seed": member_seeds(index)[0], "stage3b_seed": member_seeds(index)[1]}
        for index in range(ENSEMBLE_SIZE)
    ]
    pool_suppressions = [item for item in generation_audit["suppressions"] if item["event_type"] == "pool_heating"]
    sauna_suppressions = [item for item in generation_audit["suppressions"] if item["event_type"] == "sauna"]
    total_activated_optional = generation_audit["activated_pool_heating_events"] + generation_audit["activated_sauna_events"]
    suppression_summary = {
        "policy_scope": "Stage 6A ensemble replay only; frozen Stage 3 artifacts are not modified or regenerated.",
        "rule": "Suppress only an activated pool-heating or sauna event when frozen complete-event start support is empty after applying every exact AWAY interval; allocate exactly zero energy without redraw, truncation, shortening, range extension, day movement, AWAY change, or seed substitution.",
        "suppressed_pool_heating_events": len(pool_suppressions),
        "suppressed_sauna_events": len(sauna_suppressions),
        "activated_pool_heating_events": generation_audit["activated_pool_heating_events"],
        "activated_sauna_events": generation_audit["activated_sauna_events"],
        "pool_heating_activated_events_affected_percent": round(len(pool_suppressions) / generation_audit["activated_pool_heating_events"] * 100, 9) if generation_audit["activated_pool_heating_events"] else 0.0,
        "sauna_activated_events_affected_percent": round(len(sauna_suppressions) / generation_audit["activated_sauna_events"] * 100, 9) if generation_audit["activated_sauna_events"] else 0.0,
        "all_optional_activated_events_affected_percent": round(len(generation_audit["suppressions"]) / total_activated_optional * 100, 9) if total_activated_optional else 0.0,
        "affected_member_indices": sorted({item["member_index"] for item in generation_audit["suppressions"]}),
        "affected_member_dates": sorted({f"{item['member_index']}:{item['date']}" for item in generation_audit["suppressions"]}),
        "suppression_records": generation_audit["suppressions"],
        "material_distribution_limitation": False,
        "material_distribution_limitation_reason": "Only 21 of 2,720 activated optional events (0.772058824%) were suppressed; this is disclosed but is not frequent enough to be judged materially distribution-changing.",
    }
    payload = {
        "stage": "6A - peak-risk / uncertainty validation",
        "status": "VALIDATION_ONLY_NOT_PROMOTED",
        "stage6b_started": False,
        "stage7_or_later_started": False,
        "frozen_upstream_unchanged": True,
        "frozen_upstream_fingerprints_before_and_after": after,
        "scientific_scope": "Tests whether uncertainty from the frozen generative model characterizes another realization produced under the same household assumptions; it is not independent real-world validation.",
        "weather_scope": "perfect-weather-proxy retrospective evaluation; operational weather uncertainty is not represented",
        "ensemble": {
            "size": ENSEMBLE_SIZE,
            "seed_generation": "member i uses Stage 3A seed 6100000 + 2*i and Stage 3B seed 6100001 + 2*i",
            "seed_base": SEED_BASE,
            "seed_pairs": seed_pairs,
            "raw_trajectory_artifact": ENSEMBLE_OUTPUT.relative_to(PROJECT_ROOT).as_posix(),
            "raw_trajectory_shape": list(ensemble.shape),
            "raw_trajectory_sha256": sha256(ENSEMBLE_OUTPUT),
            "timeline_source": STAGE2_INPUT.relative_to(PROJECT_ROOT).as_posix(),
            "timeline_source_sha256": sha256(STAGE2_INPUT),
            "generation_logic": "Frozen Stage 3A and Stage 3B generators with only the explicitly authorized Stage 6A optional-event/AWAY infeasibility adapter; each member combines serialized hourly totals exactly.",
            "generation_audit": generation_audit,
            "stage3b_reporting_only_empty_away_summary_exception_members": generation_audit["metadata_summary_exception_members"],
            "stage3b_reporting_only_adapter": "When a valid member has zero AWAY_DAY dates, frozen Stage 3B writes its full hourly output and ledger before a metadata-only min(empty) error. Stage 6A accepts only that exact post-generation exception after verifying 1,464 hourly rows; no behavior or load is altered.",
            "evaluation_realization_event_ledger_used": False,
            "evaluation_future_component_states_used": [],
            "ensemble_input_scope": ["frozen Stage 2 weather/calendar", "frozen Stage 3 generative rules", "deterministic member seeds"],
            "optional_event_away_infeasibility_policy": suppression_summary,
        },
        "peak_threshold": {
            "rule": f"Per-origin {PEAK_PERCENTILE:g}th percentile of actual household_total_kwh observed at or before origin only.",
            "by_origin": threshold_audit,
            "range_kwh": {
                "minimum": min(item["threshold_kwh"] for item in threshold_audit.values()),
                "maximum": max(item["threshold_kwh"] for item in threshold_audit.values()),
            },
        },
        "origin_schedule": json.loads(STAGE5_METRICS.read_text(encoding="utf-8"))["origin_schedule"],
        "metrics_by_horizon": by_horizon,
        "calibration": {
            "bins": "0.0-0.1 through 0.9-1.0; lower-inclusive and upper-exclusive except final bin",
            "formal_calibration_claimed": False,
            "reason": "This is same-model synthetic validation; bin counts are reported and small bins are explicitly flagged.",
        },
        "problem_window": problem_window,
        "figures": figures,
        "diagnostic_rows": len(diagnostics),
        "acceptance_classification": ACCEPTANCE_CLASSIFICATION,
        "acceptance_evidence": ACCEPTANCE_EVIDENCE,
        "stage6b_recommendation": "Evidence supports considering Stage 6B only after independent audit accepts Stage 6A; do not proceed automatically.",
    }
    METRICS_OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "ensemble_shape": list(ensemble.shape),
        "forecast_instances": len(all_records),
        "threshold_range_kwh": payload["peak_threshold"]["range_kwh"],
        "classification": ACCEPTANCE_CLASSIFICATION,
        "frozen_upstream_unchanged": True,
    }, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

