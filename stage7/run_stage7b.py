"""Build the Stage 7B production integration artifact."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "stage7" / "backend"))
sys.path.insert(0, str(ROOT))

from hackowatt_stage7.pipeline import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

