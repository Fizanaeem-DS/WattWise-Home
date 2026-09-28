"""Stage 7B validation and frozen-upstream checks."""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path

from constraints.stage7_constraints import validate_constraints
from contract.production_schema import OptimizationRequirements
from contract.schema import LoadComponent
from .config import FROZEN_UPSTREAM_FILE_COUNT, FROZEN_UPSTREAM_TREE_SHA256, ROOT


def frozen_upstream_identity(root: Path = ROOT) -> tuple[int, str]:
    """Hash the exact pre-Stage-7B source/artifact surface."""

    included = ["README.md", ".gitignore", "data", "docs", "models", "scripts", "src", "tests"]
    files: list[Path] = []
    for name in included:
        path = root / name
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(item for item in path.rglob("*") if item.is_file())
    filtered = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts or ".pytest_cache" in path.parts:
            continue
        if "/hackowatt_stage7/" in f"/{rel}/" or "stage7b" in rel.lower():
            continue
        filtered.append(path)
    records = []
    for path in sorted(set(filtered)):
        records.append(f"{path.relative_to(root).as_posix()}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
    return len(records), hashlib.sha256("\n".join(records).encode()).hexdigest()


def validate_requirements(requirements: OptimizationRequirements) -> dict:
    problems = validate_constraints()
    ids = [event.event_id for event in requirements.events]
    if len(ids) != len(set(ids)):
        problems.append("production event IDs are not unique")
    if requirements.mock_generator_used or requirements.source != "real":
        problems.append("production requirements have mock provenance")
    if any(event.energy_kwh < 0 or event.duration_hours < 0 or event.power_kw < 0 for event in requirements.events):
        problems.append("negative event quantity")
    for event in requirements.events:
        if event.component in {LoadComponent.DISHWASHER, LoadComponent.WASHER, LoadComponent.DRYER,
                               LoadComponent.SAUNA, LoadComponent.POOL_HEATING} and not event.coherent_cycle:
            problems.append(f"{event.event_id}: coherent cycle lost")
    frozen_count, frozen_hash = frozen_upstream_identity()
    if frozen_count != FROZEN_UPSTREAM_FILE_COUNT or frozen_hash != FROZEN_UPSTREAM_TREE_SHA256:
        problems.append("frozen Stage 1-6B or Stage 8 source/artifact bytes changed")
    counts = Counter(event.component.value for event in requirements.events)
    return {
        "status": "PASS" if not problems else "FAIL",
        "problems": problems,
        "event_count": len(requirements.events),
        "event_counts_by_component": dict(sorted(counts.items())),
        "hvac_hour_state_count": len(requirements.hvac.hourly_states),
        "mock_generator_used": requirements.mock_generator_used,
        "frozen_upstream": {
            "file_count": frozen_count,
            "tree_sha256": frozen_hash,
            "expected_file_count": FROZEN_UPSTREAM_FILE_COUNT,
            "expected_tree_sha256": FROZEN_UPSTREAM_TREE_SHA256,
            "byte_identical": frozen_count == FROZEN_UPSTREAM_FILE_COUNT and frozen_hash == FROZEN_UPSTREAM_TREE_SHA256,
        },
    }

