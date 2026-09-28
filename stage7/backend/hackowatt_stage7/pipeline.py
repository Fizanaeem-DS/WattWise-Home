"""Materialize and validate the Stage 7B production requirements."""

from __future__ import annotations

import json

from .config import OUTPUT_PATH, REPORT_PATH
from .production import build_optimization_requirements
from .validate import validate_requirements


def main() -> int:
    requirements = build_optimization_requirements()
    report = validate_requirements(requirements)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(requirements.to_dict(), indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1

