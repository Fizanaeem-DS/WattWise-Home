"""Launch the real Streamlit app and exercise all pages plus the demo path."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src", ROOT / "app"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import plotly
import streamlit
from streamlit.testing.v1 import AppTest

PORT = 8513
PAGES = [
    "Overview", "Historical Consumption", "Forecast", "Peak Hours", "Tariff",
    "Flexibility (Stage 7)", "PV Simulator", "Optimizer",
]
DEMO_PATH = [
    "Overview", "Historical Consumption", "Forecast", "Peak Hours", "Tariff",
    "Flexibility (Stage 7)", "Optimizer", "PV Simulator",
]


def _probe(url: str, timeout: float = 1.0) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def main() -> int:
    command = [
        sys.executable, "-c", "from streamlit.web.cli import main; main()",
        "run", str(ROOT / "app" / "app.py"),
        "--global.developmentMode", "false",
        "--server.headless", "true",
        "--server.port", str(PORT),
        "--browser.gatherUsageStats", "false",
    ]
    process = subprocess.Popen(
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    health_status = None
    health_body = ""
    root_status = None
    startup_error = ""
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                startup_error = process.stdout.read() if process.stdout else "Streamlit exited before health check"
                break
            try:
                health_status, health_body = _probe(f"http://localhost:{PORT}/_stcore/health")
                root_status, _ = _probe(f"http://localhost:{PORT}/")
                break
            except Exception:
                time.sleep(.25)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    page_results: dict[str, dict[str, object]] = {}
    app = AppTest.from_file(str(ROOT / "app" / "app.py"), default_timeout=30)
    app.run()
    for index, page in enumerate(PAGES):
        if index:
            app.sidebar.radio[0].set_value(page).run()
        exceptions = [item.message for item in app.exception]
        page_results[page] = {
            "status": "PASS" if not exceptions else "FAIL",
            "exceptions": exceptions,
            "metric_count": len(app.metric),
            "dataframe_count": len(app.dataframe),
        }

    demo_results: list[dict[str, object]] = []
    for page in DEMO_PATH:
        app.sidebar.radio[0].set_value(page).run()
        if page == "Optimizer" and app.selectbox:
            app.selectbox[0].set_value("2025-08-03").run()
        exceptions = [item.message for item in app.exception]
        demo_results.append({"page": page, "status": "PASS" if not exceptions else "FAIL", "exceptions": exceptions})

    report = {
        "stage": "12 runtime and demo-path validation",
        "dependencies": {
            "python": sys.version.split()[0],
            "streamlit": streamlit.__version__,
            "plotly": plotly.__version__,
        },
        "startup": {
            "command": command,
            "http_root_status": root_status,
            "health_status": health_status,
            "health_body": health_body,
            "startup_error": startup_error,
            "status": "PASS" if health_status == 200 and health_body.strip() == "ok" and root_status == 200 else "FAIL",
        },
        "pages": page_results,
        "demo_path": demo_results,
    }
    report["status"] = "PASS" if report["startup"]["status"] == "PASS" and all(item["status"] == "PASS" for item in page_results.values()) and all(item["status"] == "PASS" for item in demo_results) else "FAIL"
    output = ROOT / "artifacts" / "stage12" / "stage12_runtime_validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Stage 12 runtime validation: {report['status']}")
    print(f"Startup: {report['startup']['status']}; pages: {sum(item['status'] == 'PASS' for item in page_results.values())}/{len(page_results)}; demo: {sum(item['status'] == 'PASS' for item in demo_results)}/{len(demo_results)}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
