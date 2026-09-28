"""Acquire and build the Stage 8 rooftop-PV production engine."""

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hackowatt_stage8.pipeline import main  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh-pvgis",
        action="store_true",
        help="retrieve fresh official PVGIS responses instead of reusing the preserved raw artifact",
    )
    args = parser.parse_args()
    raise SystemExit(main(refresh_pvgis=args.refresh_pvgis))
