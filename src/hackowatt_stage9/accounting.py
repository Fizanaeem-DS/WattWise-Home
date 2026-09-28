"""Shared current/optimized energy accounting equations."""

from __future__ import annotations

from typing import Iterable

from .config import EXPORT_PRICE_EUR_PER_KWH


def account_hour(load_kwh: float, pv_kwh: float, tariff: float) -> dict[str, float]:
    self_consumed = min(load_kwh, pv_kwh)
    grid_import = max(load_kwh - pv_kwh, 0.0)
    exported = max(pv_kwh - load_kwh, 0.0)
    import_cost = grid_import * tariff
    export_revenue = exported * EXPORT_PRICE_EUR_PER_KWH
    return {
        "self_consumed_pv_kwh": self_consumed,
        "grid_import_kwh": grid_import,
        "exported_pv_kwh": exported,
        "import_cost_eur": import_cost,
        "export_revenue_eur": export_revenue,
        "net_cost_eur": import_cost - export_revenue,
    }


def sum_field(rows: Iterable[dict], field: str) -> float:
    return sum(float(row[field]) for row in rows)

