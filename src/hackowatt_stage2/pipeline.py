"""End-to-end Stage 2 pipeline entry point."""

from __future__ import annotations

import json

from .acquire import acquire
from .process import process
from .validate import validate


def main() -> int:
    acquisition = acquire()
    dataset = process()
    report = validate()
    summary = {
        "raw_rows": acquisition["returned"]["row_count"],
        "processed_rows": dataset["row_count"],
        "validation_status": report["status"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

