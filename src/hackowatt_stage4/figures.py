"""Small dependency-free SVG chart writer for Stage 4 validation artifacts."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Iterable


COLORS = ("#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2")


def _svg_start(title: str, width: int = 1200, height: int = 520) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="Arial" font-size="20" font-weight="bold">{escape(title)}</text>',
    ]


def line_chart(
    path: Path,
    title: str,
    series: list[tuple[str, list[float]]],
    x_labels: list[str],
    y_label: str,
) -> None:
    width, height = 1200, 520
    left, right, top, bottom = 80, 25, 55, 70
    plot_w, plot_h = width - left - right, height - top - bottom
    all_values = [value for _, values in series for value in values]
    y_min, y_max = min(all_values), max(all_values)
    if y_max == y_min:
        y_max = y_min + 1
    parts = _svg_start(title, width, height)
    parts.extend([
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#111"/>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#111"/>',
        f'<text x="18" y="{top + plot_h / 2}" transform="rotate(-90 18 {top + plot_h / 2})" text-anchor="middle" font-family="Arial" font-size="13">{escape(y_label)}</text>',
    ])
    for tick in range(6):
        value = y_min + (y_max - y_min) * tick / 5
        y = top + plot_h - plot_h * tick / 5
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{value:.2f}</text>')
    count = len(x_labels)
    for index, (name, values) in enumerate(series):
        points = []
        for position, value in enumerate(values):
            x = left + (plot_w * position / max(1, count - 1))
            y = top + plot_h - (value - y_min) / (y_max - y_min) * plot_h
            points.append(f"{x:.2f},{y:.2f}")
        parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{COLORS[index % len(COLORS)]}" stroke-width="1.6"/>')
    label_positions = sorted(set([0, count // 4, count // 2, 3 * count // 4, count - 1]))
    for position in label_positions:
        x = left + plot_w * position / max(1, count - 1)
        parts.append(f'<text x="{x:.2f}" y="{top + plot_h + 22}" text-anchor="middle" font-family="Arial" font-size="10">{escape(x_labels[position])}</text>')
    legend_x = left
    for index, (name, _) in enumerate(series):
        x = legend_x + index * 185
        parts.append(f'<line x1="{x}" y1="{height - 20}" x2="{x + 24}" y2="{height - 20}" stroke="{COLORS[index % len(COLORS)]}" stroke-width="3"/>')
        parts.append(f'<text x="{x + 30}" y="{height - 16}" font-family="Arial" font-size="12">{escape(name)}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def bar_chart(
    path: Path,
    title: str,
    labels: list[str],
    values: list[float],
    y_label: str,
    colors: Iterable[str] | None = None,
) -> None:
    width, height = 1200, 520
    left, right, top, bottom = 80, 25, 55, 95
    plot_w, plot_h = width - left - right, height - top - bottom
    maximum = max(values) if values else 1
    palette = list(colors or COLORS)
    parts = _svg_start(title, width, height)
    parts.extend([
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#111"/>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#111"/>',
        f'<text x="18" y="{top + plot_h / 2}" transform="rotate(-90 18 {top + plot_h / 2})" text-anchor="middle" font-family="Arial" font-size="13">{escape(y_label)}</text>',
    ])
    for tick in range(6):
        value = maximum * tick / 5
        y = top + plot_h - plot_h * tick / 5
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{value:.2f}</text>')
    slot = plot_w / max(1, len(values))
    for index, (label, value) in enumerate(zip(labels, values)):
        bar_h = value / maximum * plot_h if maximum else 0
        x = left + index * slot + slot * 0.12
        y = top + plot_h - bar_h
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{slot * 0.76:.2f}" height="{bar_h:.2f}" fill="{palette[index % len(palette)]}"/>')
        parts.append(f'<text x="{x + slot * 0.38:.2f}" y="{top + plot_h + 18}" text-anchor="middle" font-family="Arial" font-size="10" transform="rotate(25 {x + slot * 0.38:.2f} {top + plot_h + 18})">{escape(label)}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def stacked_share_chart(path: Path, title: str, labels: list[str], values: list[float]) -> None:
    width, height = 1200, 300
    left, right, top = 75, 35, 80
    plot_w = width - left - right
    total = sum(values)
    parts = _svg_start(title, width, height)
    cursor = left
    for index, (label, value) in enumerate(zip(labels, values)):
        bar_w = plot_w * value / total
        color = COLORS[index % len(COLORS)]
        parts.append(f'<rect x="{cursor:.2f}" y="{top}" width="{bar_w:.2f}" height="70" fill="{color}"/>')
        if bar_w > 75:
            parts.append(f'<text x="{cursor + bar_w / 2:.2f}" y="{top + 42}" text-anchor="middle" font-family="Arial" font-size="12" fill="white">{value / total * 100:.1f}%</text>')
        legend_x = left + (index % 3) * 350
        legend_y = 190 + (index // 3) * 35
        parts.append(f'<rect x="{legend_x}" y="{legend_y - 13}" width="18" height="18" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 26}" y="{legend_y + 1}" font-family="Arial" font-size="13">{escape(label)} — {value:.2f} kWh</text>')
        cursor += bar_w
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
