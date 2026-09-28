"""Dependency-free SVG figures for the representative Stage 9 week."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


def _points(values: list[float], left: float, top: float, width: float, height: float, maximum: float) -> str:
    if len(values) == 1:
        return f"{left},{top + height}"
    return " ".join(
        f"{left + width * i / (len(values) - 1):.2f},{top + height * (1 - value / maximum):.2f}"
        for i, value in enumerate(values)
    )


def line_chart(path: Path, title: str, rows: list[dict[str, Any]], series: list[tuple[str, str, str]]) -> None:
    width, height, left, top = 1200, 500, 75, 65
    plot_width, plot_height = 1080, 350
    maximum = max(max(float(row[field]) for row in rows) for field, _, _ in series) * 1.08 or 1.0
    content = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="32" font-family="sans-serif" font-size="22" font-weight="bold">{escape(title)}</text>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#333"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#333"/>',
        f'<text x="12" y="{top + plot_height / 2}" font-family="sans-serif" font-size="14">kWh</text>',
    ]
    for position, (field, label, color) in enumerate(series):
        values = [float(row[field]) for row in rows]
        content.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{_points(values, left, top, plot_width, plot_height, maximum)}"/>')
        content.append(f'<line x1="{left + 220 * position}" y1="455" x2="{left + 220 * position + 28}" y2="455" stroke="{color}" stroke-width="4"/>')
        content.append(f'<text x="{left + 220 * position + 36}" y="461" font-family="sans-serif" font-size="14">{escape(label)}</text>')
    content.append(f'<text x="{left}" y="488" font-family="sans-serif" font-size="12">{escape(rows[0]["timestamp"])} to {escape(rows[-1]["timestamp"])}</text>')
    content.append('</svg>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(content) + "\n", encoding="utf-8")


def cost_chart(path: Path, rows: list[dict[str, Any]]) -> None:
    current = sum(float(row["current_net_cost_eur"]) for row in rows)
    optimized = sum(float(row["optimized_net_cost_eur"]) for row in rows)
    maximum = max(current, optimized, 0.01)
    bars = [("Current", current, "#d95f02"), ("Optimized", optimized, "#1b9e77")]
    content = ['<svg xmlns="http://www.w3.org/2000/svg" width="760" height="500" viewBox="0 0 760 500">',
               '<rect width="100%" height="100%" fill="white"/>',
               '<text x="55" y="38" font-family="sans-serif" font-size="22" font-weight="bold">Representative week net energy cost</text>']
    for index, (label, value, color) in enumerate(bars):
        x = 150 + 280 * index
        bar_height = 330 * value / maximum
        y = 420 - bar_height
        content += [f'<rect x="{x}" y="{y:.2f}" width="150" height="{bar_height:.2f}" fill="{color}"/>',
                    f'<text x="{x + 75}" y="450" text-anchor="middle" font-family="sans-serif" font-size="16">{label}</text>',
                    f'<text x="{x + 75}" y="{y - 10:.2f}" text-anchor="middle" font-family="sans-serif" font-size="16">EUR {value:.2f}</text>']
    content.append('</svg>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(content) + "\n", encoding="utf-8")

