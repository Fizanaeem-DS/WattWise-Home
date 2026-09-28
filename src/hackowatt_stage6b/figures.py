"""Deterministic app-style Stage 6B demo figure."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


def explained_demo(path: Path, operational: list[dict[str, Any]], actual: list[float]) -> None:
    width, height = 1300, 620
    left, right, top, bottom = 85, 25, 65, 95
    plot_w, plot_h = width - left - right, height - top - bottom
    count = len(operational)
    maximum = max(
        max(actual),
        max(row["p95_kwh"] for row in operational),
        max(row["point_forecast_kwh"] for row in operational),
    )

    def point(index: int, value: float) -> tuple[float, float]:
        return (
            left + plot_w * index / max(1, count - 1),
            top + plot_h - value / maximum * plot_h,
        )

    upper = [point(index, row["p90_kwh"]) for index, row in enumerate(operational)]
    lower = [point(index, row["p10_kwh"]) for index, row in reversed(list(enumerate(operational)))]
    band = " ".join(f"{x:.2f},{y:.2f}" for x, y in [*upper, *lower])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="26" text-anchor="middle" font-family="Arial" font-size="20" font-weight="bold">Stage 6B app-style forecast — Sep-13 168h window</text>',
        f'<text x="{width / 2}" y="47" text-anchor="middle" font-family="Arial" font-size="12" fill="#b91c1c">Actual demand is retrospective evaluation truth only; it is not an operational forecast input.</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#111"/>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#111"/>',
        f'<polygon points="{band}" fill="#bfdbfe" opacity="0.65" stroke="none"/>',
    ]
    for tick in range(6):
        value = maximum * tick / 5
        y = top + plot_h - plot_h * tick / 5
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{value:.2f}</text>')
    series = [
        ("Stage 5 expected", [row["point_forecast_kwh"] for row in operational], "#2563eb", 1.8),
        ("P95 high-demand potential", [row["p95_kwh"] for row in operational], "#9333ea", 1.5),
        ("Actual — retrospective truth", actual, "#111827", 2.0),
    ]
    for name, values, color, stroke_width in series:
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in (point(index, value) for index, value in enumerate(values)))
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="{stroke_width}"/>')
    top_risk = sorted(
        operational,
        key=lambda row: (-row["peak_probability"], -row["p95_kwh"], -row["point_forecast_kwh"], row["timestamp"]),
    )[:5]
    top_timestamps = {row["timestamp"] for row in top_risk}
    for index, row in enumerate(operational):
        if row["timestamp"] in top_timestamps:
            x, y = point(index, row["p95_kwh"])
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#dc2626" stroke="white" stroke-width="1"/>')
    for position in sorted({0, count // 4, count // 2, 3 * count // 4, count - 1}):
        x, _ = point(position, 0)
        label = operational[position]["timestamp"][5:16].replace("T", " ")
        parts.append(f'<text x="{x:.2f}" y="{top + plot_h + 23}" text-anchor="middle" font-family="Arial" font-size="10">{escape(label)}</text>')
    legend = [
        ("#2563eb", "Stage 5 expected"),
        ("#bfdbfe", "P10–P90 plausible band"),
        ("#9333ea", "P95 high-demand potential"),
        ("#111827", "Actual — retrospective truth"),
        ("#dc2626", "Top 5 peak-risk periods"),
    ]
    for index, (color, label) in enumerate(legend):
        x = left + index * 225
        parts.append(f'<rect x="{x}" y="{height - 29}" width="20" height="8" fill="{color}"/>')
        parts.append(f'<text x="{x + 27}" y="{height - 20}" font-family="Arial" font-size="11">{escape(label)}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")

