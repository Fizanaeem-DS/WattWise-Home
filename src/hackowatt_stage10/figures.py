"""Dependency-free, zero-based SVG figures for Stage 10."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


COLORS = {"current": "#d95f02", "optimized": "#1b9e77", "pv": "#7570b3"}


def _svg_start(title: str, width: int = 1000, height: int = 560) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="60" y="38" font-family="sans-serif" font-size="22" font-weight="bold">{escape(title)}</text>',
    ]


def line_comparison(path: Path, title: str, rows: list[dict[str, Any]], series: list[tuple[str, str, str]], unit: str) -> None:
    width, height, left, top, plot_w, plot_h = 1000, 560, 85, 75, 850, 370
    values = [float(row[field]) for row in rows for field, _, _ in series]
    y_min, y_max = min(0.0, min(values)), max(0.0, max(values))
    span = y_max - y_min or 1.0
    content = _svg_start(title, width, height)
    zero_y = top + plot_h * (y_max / span)
    content += [
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#333"/>',
        f'<line x1="{left}" y1="{zero_y:.2f}" x2="{left + plot_w}" y2="{zero_y:.2f}" stroke="#333"/>',
        f'<text x="15" y="{top + plot_h / 2}" font-family="sans-serif" font-size="14">{escape(unit)}</text>',
    ]
    for s_index, (field, label, color) in enumerate(series):
        points = []
        for index, row in enumerate(rows):
            x = left + plot_w * index / max(len(rows) - 1, 1)
            y = top + plot_h * (y_max - float(row[field])) / span
            points.append(f"{x:.2f},{y:.2f}")
            content.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{color}"/>')
        content.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="3"/>')
        lx = left + 250 * s_index
        content.append(f'<line x1="{lx}" y1="505" x2="{lx + 30}" y2="505" stroke="{color}" stroke-width="4"/>')
        content.append(f'<text x="{lx + 38}" y="511" font-family="sans-serif" font-size="14">{escape(label)}</text>')
    for index, row in enumerate(rows):
        x = left + plot_w * index / max(len(rows) - 1, 1)
        content.append(f'<text x="{x:.2f}" y="470" text-anchor="middle" font-family="sans-serif" font-size="13">{row["capacity_kwp"]:g} kWp</text>')
    content.append('<text x="935" y="548" text-anchor="end" font-family="sans-serif" font-size="11">ANNUALIZED ESTIMATE</text>')
    content.append('</svg>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(content) + "\n", encoding="utf-8")


def production_bars(path: Path, rows: list[dict[str, Any]]) -> None:
    maximum = max(float(row["annual_pv_production_kwh"]) for row in rows)
    content = _svg_start("Annual PV production versus capacity")
    for index, row in enumerate(rows):
        x = 120 + 210 * index
        height = 350 * float(row["annual_pv_production_kwh"]) / maximum
        y = 445 - height
        content += [
            f'<rect x="{x}" y="{y:.2f}" width="120" height="{height:.2f}" fill="{COLORS["pv"]}"/>',
            f'<text x="{x + 60}" y="470" text-anchor="middle" font-family="sans-serif" font-size="14">{row["capacity_kwp"]:g} kWp</text>',
            f'<text x="{x + 60}" y="{y - 9:.2f}" text-anchor="middle" font-family="sans-serif" font-size="13">{float(row["annual_pv_production_kwh"]):,.0f} kWh</text>',
        ]
    content += ['<line x1="80" y1="445" x2="940" y2="445" stroke="#333"/>',
                '<text x="940" y="548" text-anchor="end" font-family="sans-serif" font-size="11">PVGIS FROZEN ANNUAL PRODUCTION</text>', '</svg>']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(content) + "\n", encoding="utf-8")


def comparison_panel(path: Path, row: dict[str, Any]) -> None:
    panels = [
        ("PV self-consumed", "annual_pv_self_consumed_kwh", "kWh/year"),
        ("Grid imported", "annual_grid_imported_kwh", "kWh/year"),
        ("Net electricity cost", "annual_net_electricity_cost_eur", "EUR/year"),
        ("Simple payback", "simple_payback_years", "years"),
    ]
    content = _svg_start(f'Current versus optimized at {row["capacity_kwp"]:g} kWp', 1100, 720)
    for p_index, (label, field, unit) in enumerate(panels):
        top = 75 + 150 * p_index
        current = float(row[f"current_{field}"])
        optimized = float(row[f"optimized_{field}"])
        maximum = max(current, optimized, 1e-9)
        content.append(f'<text x="65" y="{top}" font-family="sans-serif" font-size="17" font-weight="bold">{escape(label)} ({escape(unit)})</text>')
        for index, (name, value, color) in enumerate((("Current", current, COLORS["current"]), ("Optimized", optimized, COLORS["optimized"]))):
            y = top + 20 + 45 * index
            length = 720 * value / maximum
            content += [f'<text x="65" y="{y + 19}" font-family="sans-serif" font-size="14">{name}</text>',
                        f'<rect x="155" y="{y}" width="{length:.2f}" height="28" fill="{color}"/>',
                        f'<text x="{165 + length:.2f}" y="{y + 20}" font-family="sans-serif" font-size="13">{value:,.2f}</text>']
    content += ['<text x="1040" y="700" text-anchor="end" font-family="sans-serif" font-size="11">ANNUALIZED ESTIMATE; ALL MINI-AXES START AT ZERO</text>', '</svg>']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(content) + "\n", encoding="utf-8")


__all__ = ["COLORS", "comparison_panel", "line_comparison", "production_bars"]
