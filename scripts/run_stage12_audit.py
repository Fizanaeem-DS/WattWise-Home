"""Persist the Stage 12 machine-readable system audit and freeze record."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hackowatt_stage12.audit import audit_system


def _optional(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def main() -> int:
    report = audit_system()
    output_dir = ROOT / "artifacts" / "stage12"
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime = _optional(output_dir / "stage12_runtime_validation.json")
    regression = _optional(output_dir / "stage12_regression_summary.json")
    report["runtime_validation"] = runtime
    report["regression_summary"] = regression
    report["overall_status"] = "PASS" if report["status"] == "PASS" and runtime and runtime.get("status") == "PASS" and regression and regression.get("stage12_tests", {}).get("status") == "PASS" else "INCOMPLETE"
    (output_dir / "stage12_validation_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fingerprint = {
        "initial_stage12_fingerprint": report["freeze"]["initial_before_defect_correction"],
        "defect_correction": {
            "required": True,
            "file": report["freeze"]["corrected_file"],
            "file_sha256": report["freeze"]["corrected_file_sha256"],
            "scope": "presentation labels and limitation wording only; no backend value or artifact changed",
        },
        "new_final_stage1_to_stage11_fingerprint": report["freeze"]["final_candidate"],
    }
    (output_dir / "stage12_frozen_tree_fingerprint.json").write_text(json.dumps(fingerprint, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Stage 12 core audit: {report['status']} ({len(report['checks'])} gates)")
    print(f"Stage 12 overall: {report['overall_status']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
