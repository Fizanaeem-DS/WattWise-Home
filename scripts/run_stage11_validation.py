"""Run the read-only Stage 11 integration validation and persist its report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hackowatt_stage11.validation import validate


def main() -> int:
    report = validate()
    output = ROOT / "artifacts" / "stage11" / "stage11_validation_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Stage 11 validation: {report['status']}")
    print(f"Validation gates: {len(report['checks'])}")
    print(f"Report: {output.relative_to(ROOT).as_posix()}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
