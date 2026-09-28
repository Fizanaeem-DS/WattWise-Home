"""Retrieve and preserve the two official PVGIS responses used by Stage 8."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import PVGIS_BASE_URL, PVGIS_SOURCE, RAW_OUTPUT, pvcalc_parameters, seriescalc_parameters


def _request(tool: str, parameters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    url = f"{PVGIS_BASE_URL}/{tool}?{urlencode(parameters)}"
    request = Request(url, headers={"User-Agent": "HackoWatt-Scenario3-Stage8/1.0"})
    with urlopen(request, timeout=90) as response:
        if response.status != 200:
            raise RuntimeError(f"STOP: PVGIS {tool} returned HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    return url, payload


def acquire() -> dict[str, Any]:
    pvcalc_params = pvcalc_parameters()
    seriescalc_params = seriescalc_parameters()
    pvcalc_url, pvcalc = _request("PVcalc", pvcalc_params)
    seriescalc_url, seriescalc = _request("seriescalc", seriescalc_params)
    if "outputs" not in pvcalc or "outputs" not in seriescalc:
        raise RuntimeError("STOP: PVGIS response does not contain expected outputs")
    artifact = {
        "source": PVGIS_SOURCE,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "requests": {
            "PVcalc": {
                "endpoint": f"{PVGIS_BASE_URL}/PVcalc",
                "request_url": pvcalc_url,
                "parameters": pvcalc_params,
                "response": pvcalc,
            },
            "seriescalc": {
                "endpoint": f"{PVGIS_BASE_URL}/seriescalc",
                "request_url": seriescalc_url,
                "parameters": seriescalc_params,
                "response": seriescalc,
            },
        },
    }
    RAW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    RAW_OUTPUT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def load_or_acquire(refresh: bool = False) -> dict[str, Any]:
    if refresh or not RAW_OUTPUT.exists():
        return acquire()
    return json.loads(RAW_OUTPUT.read_text(encoding="utf-8"))
