"""Run the controlled Stage 5B peak-aware forecasting experiment."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hackowatt_stage5b.pipeline import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

