"""Dependency-free deterministic SVG figures for Stage 8."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def monthly_chart(path: Path, rows: list[dict[str, Any]]) -> None:
    width, height = 1050, 560
    left, right, top, bottom = 75, 25, 55, 70
    plot_w, plot_h = width - left - right, height - top - bottom
    values = [float(row["monthly_generation_kwh_per_kwp"]) for row in rows]
    maximum = max(values) * 1.1
    bar_w = plot_w / len(values) * 0.66
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="Arial" font-size="20" font-weight="bold">Barcelona rooftop PV — monthly generation per 1 kWp</text>',
        f'<text x="{width / 2}" y="47" text-anchor="middle" font-family="Arial" font-size="12" fill="#475569">PVGIS 5.3 PVcalc, fixed 30° south-facing crystalline-silicon system, 14% losses</text>',
    ]
    for tick in range(5):
        value = maximum * tick / 4
        y = top + plot_h - plot_h * tick / 4
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#e2e8f0"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{value:.0f}</text>')
    for index, value in enumerate(values):
        centre = left + plot_w * (index + 0.5) / len(values)
        y = top + plot_h - value / maximum * plot_h
        parts.append(f'<rect x="{centre - bar_w / 2:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{top + plot_h - y:.2f}" fill="#f59e0b"/>')
        parts.append(f'<text x="{centre:.2f}" y="{top + plot_h + 20}" text-anchor="middle" font-family="Arial" font-size="11">{index + 1}</text>')
        parts.append(f'<text x="{centre:.2f}" y="{y - 6:.2f}" text-anchor="middle" font-family="Arial" font-size="10">{value:.1f}</text>')
    parts.extend([
        f'<text x="{width / 2}" y="{height - 13}" text-anchor="middle" font-family="Arial" font-size="12">Month</text>',
        f'<text x="18" y="{top + plot_h / 2}" transform="rotate(-90 18 {top + plot_h / 2})" text-anchor="middle" font-family="Arial" font-size="12">kWh per 1 kWp</text>',
        '</svg>',
    ])
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def profile_chart(path: Path, rows: list[dict[str, Any]]) -> None:
    width, height = 1300, 560
    left, right, top, bottom = 80, 25, 60, 75
    plot_w, plot_h = width - left - right, height - top - bottom
    values = [float(row["pv_generation_kwh_per_kwp"]) for row in rows]
    maximum = max(values) * 1.05

    def point(index: int, value: float) -> tuple[float, float]:
        return left + plot_w * index / (len(values) - 1), top + plot_h - value / maximum * plot_h

    points = " ".join(f"{x:.2f},{y:.2f}" for x, y in (point(i, value) for i, value in enumerate(values)))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="Arial" font-size="20" font-weight="bold">Barcelona rooftop PV — Aug–Sep hourly profile per 1 kWp</text>',
        f'<text x="{width / 2}" y="48" text-anchor="middle" font-family="Arial" font-size="12" fill="#475569">Latest complete PVGIS SARAH3 source year (2023), UTC converted and calendar-aligned to the frozen 2025 timeline</text>',
    ]
    for tick in range(5):
        value = maximum * tick / 4
        y = top + plot_h - plot_h * tick / 4
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#e2e8f0"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{value:.2f}</text>')
    parts.append(f'<polyline points="{points}" fill="none" stroke="#f59e0b" stroke-width="1.15"/>')
    for position in (0, 31 * 24, len(rows) - 1):
        x, _ = point(position, 0)
        label = rows[position]["timestamp"][5:16].replace("T", " ")
        parts.append(f'<text x="{x:.2f}" y="{top + plot_h + 22}" text-anchor="middle" font-family="Arial" font-size="11">{label}</text>')
    parts.extend([
        f'<text x="{width / 2}" y="{height - 13}" text-anchor="middle" font-family="Arial" font-size="12">Frozen 2025 Europe/Madrid timestamp</text>',
        f'<text x="18" y="{top + plot_h / 2}" transform="rotate(-90 18 {top + plot_h / 2})" text-anchor="middle" font-family="Arial" font-size="12">kWh/h per 1 kWp</text>',
        '</svg>',
    ])
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
