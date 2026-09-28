"""Generate full stochastic-twin trajectories using frozen Stage 3 logic."""

from __future__ import annotations

import csv
from pathlib import Path
import tempfile

import numpy as np

from hackowatt_stage3a.generator import generate as generate_stage3a
from hackowatt_stage3b.generator import generate as generate_stage3b

from .config import ENSEMBLE_SIZE, STAGE2_INPUT, member_seeds
from .policy import OptionalEventAwayPolicy


def _read_totals(path: Path, column: str) -> tuple[list[str], np.ndarray]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [row["timestamp"] for row in rows], np.asarray([float(row[column]) for row in rows], dtype=float)


def generate_member(member_index: int, stage2_path: Path = STAGE2_INPUT) -> tuple[list[str], np.ndarray, dict]:
    """Generate one member without reading frozen Stage 3A/B/C artifacts or ledgers."""
    seed_a, seed_b = member_seeds(member_index)
    with tempfile.TemporaryDirectory(prefix=f"stage6a_{member_index:03d}_") as directory:
        root = Path(directory)
        stage3a_hourly = root / "stage3a.csv"
        stage3a_ledger = root / "stage3a_ledger.json"
        stage3a_metadata = root / "stage3a_metadata.json"
        stage3b_hourly = root / "stage3b.csv"
        stage3b_ledger = root / "stage3b_ledger.json"
        stage3b_metadata = root / "stage3b_metadata.json"
        generate_stage3a(
            stage2_path=stage2_path,
            hourly_output=stage3a_hourly,
            ledger_output=stage3a_ledger,
            metadata_output=stage3a_metadata,
            seed=seed_a,
        )
        metadata_empty_away_summary = False
        policy = OptionalEventAwayPolicy()
        with policy.installed():
            try:
                generate_stage3b(
                    stage2_path=stage2_path,
                    stage3a_path=stage3a_hourly,
                    stage3a_ledger_path=stage3a_ledger,
                    stage3a_metadata_path=stage3a_metadata,
                    hourly_output=stage3b_hourly,
                    ledger_output=stage3b_ledger,
                    metadata_output=stage3b_metadata,
                    seed=seed_b,
                )
            except ValueError as error:
                # Frozen Stage 3B writes the complete hourly trajectory and ledger
                # before summarizing AWAY_DAY circulation runtimes. For a valid
                # realization with zero AWAY_DAY dates, that reporting-only min()
                # call has an empty input. Accept only this exact post-generation
                # condition; all behavioral generation remains untouched.
                if str(error) != "min() iterable argument is empty" or not stage3b_hourly.is_file() or not stage3b_ledger.is_file():
                    raise
                metadata_empty_away_summary = True
        ledger = policy.annotate_ledger(stage3b_ledger)
        timestamps_a, totals_a = _read_totals(stage3a_hourly, "stage3a_total_kwh")
        timestamps_b, totals_b = _read_totals(stage3b_hourly, "stage3b_total_kwh")
        if timestamps_a != timestamps_b:
            raise RuntimeError(f"Generated Stage 3A/3B timelines differ for ensemble member {member_index}")
        if len(timestamps_a) != 1_464:
            raise RuntimeError(f"Ensemble member {member_index} did not produce 1,464 hourly rows")
        suppressions = []
        for record in policy.suppressions:
            enriched = dict(record)
            enriched.update({
                "member_index": member_index,
                "stage3a_seed": seed_a,
                "stage3b_seed": seed_b,
            })
            suppressions.append(enriched)
        audit = {
            "metadata_empty_away_summary": metadata_empty_away_summary,
            "suppressions": suppressions,
            "activated_pool_heating_events": len(ledger["pool_heating_events"]),
            "activated_sauna_events": len(ledger["sauna_events"]),
        }
        return timestamps_a, totals_a + totals_b, audit


def generate_ensemble(ensemble_size: int = ENSEMBLE_SIZE) -> tuple[list[str], np.ndarray, dict]:
    timestamps: list[str] | None = None
    members: list[np.ndarray] = []
    metadata_summary_exception_members: list[int] = []
    suppressions: list[dict] = []
    activated_pool_heating_events = 0
    activated_sauna_events = 0
    for member_index in range(ensemble_size):
        member_timestamps, demand, audit = generate_member(member_index)
        if audit["metadata_empty_away_summary"]:
            metadata_summary_exception_members.append(member_index)
        suppressions.extend(audit["suppressions"])
        activated_pool_heating_events += audit["activated_pool_heating_events"]
        activated_sauna_events += audit["activated_sauna_events"]
        if timestamps is None:
            timestamps = member_timestamps
        elif member_timestamps != timestamps:
            raise RuntimeError(f"Timeline mismatch in ensemble member {member_index}")
        members.append(demand)
        if (member_index + 1) % 20 == 0 or member_index + 1 == ensemble_size:
            print(f"Stage 6A ensemble: {member_index + 1}/{ensemble_size} members", flush=True)
    if timestamps is None:
        raise ValueError("Ensemble must contain at least one member")
    generation_audit = {
        "metadata_summary_exception_members": metadata_summary_exception_members,
        "suppressions": suppressions,
        "activated_pool_heating_events": activated_pool_heating_events,
        "activated_sauna_events": activated_sauna_events,
    }
    return timestamps, np.vstack(members), generation_audit

