"""Run the frozen Stage 3A digital-twin generator."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hackowatt_stage3a.pipeline import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

