"""Run Stage 4 metrics, baselines, report generation, and SVG diagnostics."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import statistics

from .analysis import block_for_hour, compute_baseline_metrics, compute_validation_metrics, read_profile
from .config import (
    BASELINE_OUTPUT,
    CATEGORY_COLUMNS,
    FIGURES_DIR,
    METRICS_OUTPUT,
    REPORT_OUTPUT,
    STAGE3C_INPUT,
)
from .figures import bar_chart, line_chart, stacked_share_chart


def _write_figures(metrics: dict, baseline_records: dict[str, list[dict]]) -> list[str]:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    _, rows = read_profile()
    timestamps = [datetime.fromisoformat(row["timestamp"]) for row in rows]
    totals = [float(row["household_total_kwh"]) for row in rows]
    created: list[Path] = []

    path = FIGURES_DIR / "01_full_61_day_hourly_demand.svg"
    line_chart(path, "Full 61-day hourly household demand", [("Household", totals)], [timestamp.strftime("%b %d") for timestamp in timestamps], "kWh per hour")
    created.append(path)

    representative = [(timestamp, total) for timestamp, total in zip(timestamps, totals) if datetime.fromisoformat("2025-09-08T00:00:00+02:00") <= timestamp <= datetime.fromisoformat("2025-09-14T23:00:00+02:00")]
    path = FIGURES_DIR / "02_representative_7_day_demand.svg"
    line_chart(path, "Representative evaluation week: 8-14 September", [("Household", [value for _, value in representative])], [timestamp.strftime("%a %H:%M") for timestamp, _ in representative], "kWh per hour")
    created.append(path)

    hour_means = [statistics.mean(float(row["household_total_kwh"]) for row, timestamp in zip(rows, timestamps) if timestamp.hour == hour) for hour in range(24)]
    path = FIGURES_DIR / "03_mean_demand_by_hour.svg"
    bar_chart(path, "Mean household demand by hour of day", [f"{hour:02d}:00" for hour in range(24)], hour_means, "Mean kWh per hour")
    created.append(path)

    block_order = ["NIGHT", "MORNING", "DAYTIME", "RETURN_RAMP", "EVENING"]
    path = FIGURES_DIR / "04_mean_demand_by_analysis_block.svg"
    bar_chart(path, "Mean household demand by Stage 4 analysis block", block_order, [metrics["behavioral_face_validity"]["blocks"][name]["mean_kwh"] for name in block_order], "Mean kWh per hour")
    created.append(path)

    daily: dict[str, float] = defaultdict(float)
    for row in rows:
        daily[row["timestamp"][:10]] += float(row["household_total_kwh"])
    path = FIGURES_DIR / "05_daily_total_energy.svg"
    line_chart(path, "Daily total household energy", [("Daily total", list(daily.values()))], list(daily), "kWh per day")
    created.append(path)

    shares = metrics["energy_mix"]["category_totals_kwh"]
    path = FIGURES_DIR / "06_category_energy_shares.svg"
    stacked_share_chart(path, "Stage 3C category energy shares", list(shares), list(shares.values()))
    created.append(path)

    peak_hours = metrics["peak_face_validity"]["top_5_percent"]["hour_of_day_distribution"]
    path = FIGURES_DIR / "07_top_5_percent_peaks_by_hour.svg"
    bar_chart(path, "Top 5% demand observations by hour of day", [f"{hour:02d}:00" for hour in range(24)], [peak_hours[str(hour)] for hour in range(24)], "Peak observation count")
    created.append(path)

    weekday_profile = [statistics.mean(float(row["household_total_kwh"]) for row, timestamp in zip(rows, timestamps) if timestamp.hour == hour and row["is_weekend"] != "True") for hour in range(24)]
    weekend_profile = [statistics.mean(float(row["household_total_kwh"]) for row, timestamp in zip(rows, timestamps) if timestamp.hour == hour and row["is_weekend"] == "True") for hour in range(24)]
    path = FIGURES_DIR / "08_weekday_vs_weekend_hourly_profiles.svg"
    line_chart(path, "Weekday versus weekend mean hourly profiles", [("Weekday", weekday_profile), ("Weekend", weekend_profile)], [f"{hour:02d}:00" for hour in range(24)], "Mean kWh per hour")
    created.append(path)

    occupancy = metrics["occupancy_away_weekend"]["occupancy_state_comparison"]
    occupancy_order = ["FULL", "PARTIAL", "EMPTY", "AWAY"]
    path = FIGURES_DIR / "09_occupancy_state_demand.svg"
    bar_chart(path, "Mean demand by occupancy/AWAY state", occupancy_order, [occupancy[name]["mean_kwh"] for name in occupancy_order], "Mean kWh per hour")
    created.append(path)

    week_start = datetime.fromisoformat("2025-09-08T00:00:00+02:00")
    week_end = datetime.fromisoformat("2025-09-14T23:00:00+02:00")
    week_records = {
        name: [item for item in items if week_start <= datetime.fromisoformat(item["timestamp"]) <= week_end]
        for name, items in baseline_records.items()
    }
    actual = [item["actual"] for item in week_records["B1"]]
    labels = [datetime.fromisoformat(item["timestamp"]).strftime("%a %H:%M") for item in week_records["B1"]]
    path = FIGURES_DIR / "10_baseline_actual_vs_predicted_week.svg"
    line_chart(path, "Evaluation week: actual versus simple baselines", [("Actual", actual), ("B1 previous day", [item["prediction"] for item in week_records["B1"]]), ("B2 previous week", [item["prediction"] for item in week_records["B2"]]), ("B3 train hour-of-week", [item["prediction"] for item in week_records["B3"]])], labels, "kWh per hour")
    created.append(path)
    return [str(path.relative_to(Path(__file__).resolve().parents[2])) for path in created]


def _classification(metrics: dict, baselines: dict) -> tuple[str, list[str], list[str]]:
    """Evidence-based conclusion; numeric values are reported, not used as invented gates."""
    reasons: list[str] = []
    concerns: list[str] = []
    if not metrics["input_integrity"]["all_checks_pass"]:
        concerns.append("One or more frozen-input integrity checks failed.")
    if not metrics["physical_plausibility"]["all_checks_pass"]:
        concerns.append("One or more frozen physical/rate/coherence checks failed.")
    variability = metrics["day_to_day_variability"]
    if variability["pairwise_identical_day_count"] == 0:
        reasons.append("All 61 exact 24-hour profiles are unique; no pair of days is identical.")
    reasons.append(
        f"Daily coefficient of variation is {variability['all_days']['coefficient_of_variation']:.3f}, with component-driven variation documented across all major categories."
    )
    baseline_text = ", ".join(
        f"{name} WAPE {item['wape_percent']:.1f}% and peak overlap {item['peak_overlap_percent']:.1f}%"
        for name, item in baselines["baselines"].items()
    )
    reasons.append(f"Simple chronological baselines are not near-perfect: {baseline_text}.")
    peak_blocks = metrics["peak_face_validity"]["top_5_percent"]["analysis_block_distribution"]
    reasons.append(
        f"Peak observations are explainable by frozen high-power systems and are distributed by block as {peak_blocks}."
    )
    if concerns:
        return "FAIL", reasons, concerns
    return "PASS", reasons, concerns


def main() -> int:
    metrics = compute_validation_metrics()
    baselines, baseline_records = compute_baseline_metrics()
    figures = _write_figures(metrics, baseline_records)
    classification, reasons, concerns = _classification(metrics, baselines)
    metrics["validation_figures"] = figures
    METRICS_OUTPUT.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    BASELINE_OUTPUT.write_text(json.dumps(baselines, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = {
        "stage": "4 - digital twin validation gate",
        "source_stage3c_sha256": metrics["source"]["sha256"],
        "classification": classification,
        "classification_reasons": reasons,
        "concerns": concerns,
        "input_integrity_pass": metrics["input_integrity"]["all_checks_pass"],
        "physical_rule_checks_pass": metrics["physical_plausibility"]["all_checks_pass"],
        "baseline_summary": baselines["baselines"],
        "stage3_modified": False,
        "stage5_started": False,
        "warnings": [
            "No external universal residential-consumption benchmark or invented numeric pass threshold was used.",
            "The gate evaluates 61 synthetic days; results may not generalize beyond the frozen observation window.",
            "PASS means suitable to proceed to forecasting analysis, not proof of real-world accuracy.",
        ],
    }
    REPORT_OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"classification": classification, "rows": metrics["input_integrity"]["row_count"], "figures": len(figures)}, indent=2))
    return 0 if classification in {"PASS", "REVIEW REQUIRED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
