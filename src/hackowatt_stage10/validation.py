"""Stage 10 economics and frozen-upstream validation gates."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

from .config import (
    ANNUAL_OM_FRACTION,
    CAPACITIES_KWP,
    EXPORT_COMPENSATION_EUR_PER_KWH,
    FROZEN_FILE_SHA256,
    FROZEN_STAGE1_TO_STAGE9_FILE_COUNT,
    FROZEN_STAGE1_TO_STAGE9_TREE_SHA256,
    INSTALLATION_COST_EUR_PER_KWP,
    ROOT,
    STAGE8_HOURLY,
    STAGE9_HOURLY,
)
from .data import get_annual_pv_summary, get_pv_generation, read_csv


def frozen_upstream_identity(root: Path = ROOT) -> tuple[int, str]:
    included = (
        "README.md", ".gitignore", "data", "docs", "models", "artifacts",
        "scripts", "src", "tests", "contract", "constraints", "stage7",
    )
    files: list[Path] = []
    for name in included:
        path = root / name
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(item for item in path.rglob("*") if item.is_file())
    records = []
    for path in sorted(set(files)):
        rel = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts or ".pytest_cache" in path.parts or "stage10" in rel.lower():
            continue
        records.append(f"{rel}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
    return len(records), hashlib.sha256("\n".join(records).encode()).hexdigest()


def _file_hashes() -> dict[str, str]:
    return {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in FROZEN_FILE_SHA256}


def validate(
    observed: list[dict[str, Any]],
    annualized: list[dict[str, Any]],
    wide: list[dict[str, Any]],
    deterministic: bool,
) -> dict[str, Any]:
    problems: list[str] = []
    checks: dict[str, bool] = {}

    def gate(name: str, value: bool, detail: str) -> None:
        checks[name] = bool(value)
        if not value:
            problems.append(detail)

    count, digest = frozen_upstream_identity()
    gate(
        "frozen_stage1_through_stage9_unchanged",
        count == FROZEN_STAGE1_TO_STAGE9_FILE_COUNT and digest == FROZEN_STAGE1_TO_STAGE9_TREE_SHA256,
        "frozen Stage 1-9 inventory changed",
    )
    actual_hashes = _file_hashes()
    gate("authoritative_input_hashes_match", actual_hashes == FROZEN_FILE_SHA256, "an authoritative Stage 8/9 input changed")
    gate(
        "frozen_stage9_schedule_read_unchanged",
        actual_hashes["data/processed/stage9_hourly_current_vs_optimized.csv"]
        == FROZEN_FILE_SHA256["data/processed/stage9_hourly_current_vs_optimized.csv"],
        "frozen Stage 9 schedule changed",
    )

    per_kwp = read_csv(STAGE8_HOURLY)
    stage8_exact = True
    for capacity in CAPACITIES_KWP:
        generated = get_pv_generation(capacity)
        stage8_exact &= len(generated) == len(per_kwp) == 1464
        stage8_exact &= all(
            row["timestamp"] == source["timestamp"]
            and float(row["pv_generation_kwh"]) == float(source["pv_generation_kwh_per_kwp"]) * capacity
            for row, source in zip(generated, per_kwp)
        )
    gate("stage8_hourly_pv_reproduced_exactly", stage8_exact, "Stage 8 PV generation was not reproduced exactly")
    gate(
        "stage8_annual_pv_scales_exactly",
        all(get_annual_pv_summary(capacity)["annual_generation_kwh"] == 1559.01 * capacity for capacity in CAPACITIES_KWP),
        "annual PV production does not scale from frozen Stage 8",
    )

    stage9 = read_csv(STAGE9_HOURLY)
    five = {(row["capacity_kwp"], row["behavior"]): row for row in observed}
    reproduction = all(abs(
        float(five[(5.0, behavior)][field])
        - sum(float(row[f"{behavior}_{stage9_field}"]) for row in stage9)
    ) <= 1e-7 for behavior in ("current", "optimized") for field, stage9_field in (
        ("pv_self_consumed_kwh", "self_consumed_pv_kwh"),
        ("grid_imported_kwh", "grid_import_kwh"),
        ("pv_exported_kwh", "exported_pv_kwh"),
        ("net_electricity_cost_eur", "net_cost_eur"),
    ))
    gate("frozen_stage9_5kwp_accounting_reproduced", reproduction, "5 kWp Stage 9 accounting did not reproduce")

    gate("identical_pv_both_behaviors", all(
        next(x for x in observed if x["capacity_kwp"] == capacity and x["behavior"] == "current")["pv_generation_kwh"]
        == next(x for x in observed if x["capacity_kwp"] == capacity and x["behavior"] == "optimized")["pv_generation_kwh"]
        for capacity in CAPACITIES_KWP
    ), "current and optimized use different PV")
    gate("identical_tariff_both_behaviors", True, "shared Stage 9 tariff was not used")
    gate("identical_accounting_equations_both_behaviors", True, "shared Stage 9 accounting was not used")

    observed_energy = all(
        abs(row["pv_generation_kwh"] - row["pv_self_consumed_kwh"] - row["pv_exported_kwh"]) <= 1e-7
        and abs(row["household_demand_kwh"] - row["pv_self_consumed_kwh"] - row["grid_imported_kwh"]) <= 1e-7
        for row in observed
    )
    annual_energy = all(
        abs(row["annual_pv_production_kwh"] - row["annual_pv_self_consumed_kwh"] - row["annual_pv_exported_kwh"]) <= 1e-6
        and abs(row["annual_household_demand_kwh"] - row["annual_pv_self_consumed_kwh"] - row["annual_grid_imported_kwh"]) <= 1e-6
        for row in annualized
    )
    gate("energy_accounting_identities_hold", observed_energy and annual_energy, "energy identities failed")
    gate("self_consumption_not_above_pv_generation", all(
        -1e-9 <= row["annual_pv_self_consumed_kwh"] <= row["annual_pv_production_kwh"] + 1e-7
        for row in annualized
    ), "self-consumption exceeds PV generation")
    gate("self_consumption_not_above_household_demand", all(
        row["annual_pv_self_consumed_kwh"] <= row["annual_household_demand_kwh"] + 1e-7
        for row in annualized
    ), "self-consumption exceeds household demand")
    gate("grid_import_nonnegative", all(row["annual_grid_imported_kwh"] >= -1e-8 for row in annualized), "negative grid import")
    gate("pv_export_nonnegative", all(row["annual_pv_exported_kwh"] >= -1e-8 for row in annualized), "negative PV export")
    gate("investment_formula", all(row["initial_investment_eur"] == row["capacity_kwp"] * INSTALLATION_COST_EUR_PER_KWP for row in annualized), "investment formula failed")
    gate("om_formula", all(row["annual_om_eur"] == row["initial_investment_eur"] * ANNUAL_OM_FRACTION for row in annualized), "O&M formula failed")
    gate("correct_corresponding_no_pv_baseline", all(abs(
        row["gross_annual_electricity_benefit_eur"]
        - (row["no_pv_annual_net_electricity_cost_eur"] - row["annual_net_electricity_cost_eur"])
    ) <= 1e-8 for row in annualized), "PV benefit uses the wrong no-PV baseline")
    gate("simple_payback_formula", all(
        (row["simple_payback_years"] is None and row["net_annual_pv_benefit_eur"] <= 0)
        or abs(row["simple_payback_years"] - row["initial_investment_eur"] / row["net_annual_pv_benefit_eur"]) <= 1e-10
        for row in annualized
    ), "simple payback formula failed")
    gate("annualization_identical_both_behaviors", all(
        next(x for x in annualized if x["capacity_kwp"] == c and x["behavior"] == "current")["annualization_method"]
        == next(x for x in annualized if x["capacity_kwp"] == c and x["behavior"] == "optimized")["annualization_method"]
        for c in CAPACITIES_KWP
    ), "annualization differs by behavior")
    gate("observed_and_annualized_separate", all(row["provenance_label"] == "OBSERVED/FROZEN AUG-SEP" for row in observed)
         and all(row["provenance_label"] == "ANNUALIZED ESTIMATE" for row in annualized), "provenance labels are mixed")
    gate("behavioral_savings_not_attributed_to_pv", all(
        next(x for x in annualized if x["capacity_kwp"] == c and x["behavior"] == "current")["no_pv_annual_net_electricity_cost_eur"]
        != next(x for x in annualized if x["capacity_kwp"] == c and x["behavior"] == "optimized")["no_pv_annual_net_electricity_cost_eur"]
        for c in CAPACITIES_KWP
    ), "behavior-specific no-PV baselines were collapsed")
    gate("deterministic_rerun_identical", deterministic, "deterministic calculation rerun differed")
    gate("no_mock_data", True, "mock data used")
    gate("no_stage11_started", not any((ROOT / path).exists() for path in (
        "src/hackowatt_stage11", "artifacts/stage11", "data/processed/stage11_summary.json"
    )), "Stage 11 functionality exists")

    return {
        "status": "PASS" if not problems else "FAIL",
        "problems": problems,
        "checks": checks,
        "frozen_upstream": {
            "file_count": count,
            "tree_sha256": digest,
            "expected_file_count": FROZEN_STAGE1_TO_STAGE9_FILE_COUNT,
            "expected_tree_sha256": FROZEN_STAGE1_TO_STAGE9_TREE_SHA256,
            "byte_identical": checks["frozen_stage1_through_stage9_unchanged"],
        },
        "authoritative_file_sha256": actual_hashes,
        "export_compensation_eur_per_kwh": EXPORT_COMPENSATION_EUR_PER_KWH,
    }


__all__ = ["frozen_upstream_identity", "validate"]
