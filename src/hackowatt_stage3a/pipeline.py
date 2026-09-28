"""Run Stage 3A generation followed by validation."""

from __future__ import annotations

import json

from .generator import generate
from .validate import validate


def main() -> int:
    metadata = generate()
    report = validate()
    print(
        json.dumps(
            {
                "rows": metadata["row_count"],
                "total_kwh": metadata["stage3a_total_energy_kwh"],
                "validation_status": report["status"],
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

