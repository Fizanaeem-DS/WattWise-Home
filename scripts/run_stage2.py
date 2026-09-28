"""Run the reproducible Stage 2 acquisition, processing, and validation pipeline."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hackowatt_stage2.pipeline import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

