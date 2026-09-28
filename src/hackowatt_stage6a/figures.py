"""Stage 6A-specific deterministic SVG diagnostics."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


COLORS = ("#111827", "#2563eb", "#16a34a", "#ea580c", "#9333ea")


def sep13_peak_risk_chart(path: Path, records: list[dict[str, Any]]) -> None:
    width, height = 1300, 600
    left, right, top, bottom = 85, 25, 55, 85
    plot_w, plot_h = width - left - right, height - top - bottom
    series = [
        ("Actual", [record["actual_household_kwh"] for record in records]),
        ("Frozen Stage 5", [record["stage5_point_forecast_kwh"] for record in records]),
        ("Ensemble P50", [record["ensemble_p50_kwh"] for record in records]),
        ("Ensemble P90", [record["ensemble_p90_kwh"] for record in records]),
        ("Ensemble P95", [record["ensemble_p95_kwh"] for record in records]),
    ]
    maximum = max(value for _, values in series for value in values)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="Arial" font-size="20" font-weight="bold">Sep-13 168h peak-risk validation</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#111"/>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#111"/>',
        f'<text x="18" y="{top + plot_h / 2}" transform="rotate(-90 18 {top + plot_h / 2})" text-anchor="middle" font-family="Arial" font-size="13">kWh per hour</text>',
    ]
    for tick in range(6):
        value = maximum * tick / 5
        y = top + plot_h - plot_h * tick / 5
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{value:.2f}</text>')
    count = len(records)
    for series_index, (name, values) in enumerate(series):
        points = []
        for index, value in enumerate(values):
            x = left + plot_w * index / max(1, count - 1)
            y = top + plot_h - value / maximum * plot_h
            points.append(f"{x:.2f},{y:.2f}")
        parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{COLORS[series_index]}" stroke-width="{2.0 if series_index == 0 else 1.4}"/>')
    for index, record in enumerate(records):
        if not record["top_10_percent_peak_risk"]:
            continue
        x = left + plot_w * index / max(1, count - 1)
        y = top + plot_h - record["actual_household_kwh"] / maximum * plot_h
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.2" fill="#dc2626" stroke="white" stroke-width="0.8"/>')
    for position in sorted({0, count // 4, count // 2, 3 * count // 4, count - 1}):
        x = left + plot_w * position / max(1, count - 1)
        label = records[position]["timestamp"][5:16].replace("T", " ")
        parts.append(f'<text x="{x:.2f}" y="{top + plot_h + 24}" text-anchor="middle" font-family="Arial" font-size="10">{escape(label)}</text>')
    for index, (name, _) in enumerate(series):
        x = left + index * 205
        parts.append(f'<line x1="{x}" y1="{height - 25}" x2="{x + 24}" y2="{height - 25}" stroke="{COLORS[index]}" stroke-width="3"/>')
        parts.append(f'<text x="{x + 30}" y="{height - 21}" font-family="Arial" font-size="12">{escape(name)}</text>')
    parts.append(f'<circle cx="{left + 1040}" cy="{height - 25}" r="4" fill="#dc2626"/>')
    parts.append(f'<text x="{left + 1050}" y="{height - 21}" font-family="Arial" font-size="12">Top 10% peak-risk hour</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")

