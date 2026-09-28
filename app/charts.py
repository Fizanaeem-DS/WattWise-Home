"""Presentation-only Plotly builders for frozen Stage 11 contract data."""

from __future__ import annotations

from collections import defaultdict

import plotly.graph_objects as go

from hackowatt_stage11.models import (
    FlexibilityItem,
    ForecastBundle,
    HistoricalHourPoint,
    OptimizationHourPoint,
    PVEconomicsRow,
    TARIFF_BANDS_EUR_PER_KWH,
)
import theme


def daily_total_chart(history: tuple[HistoricalHourPoint, ...], days: int) -> go.Figure:
    by_day: dict[str, float] = defaultdict(float)
    for point in history:
        by_day[point.timestamp[:10]] += point.total_kwh
    selected = sorted(by_day)[-days:]
    fig = go.Figure(go.Scatter(
        x=selected, y=[by_day[day] for day in selected], mode="lines+markers",
        line=dict(color=theme.CATEGORICAL[0], width=2), fill="tozeroy",
        fillcolor="rgba(42,120,214,0.08)", name="Household demand",
        hovertemplate="%{x}<br>%{y:.2f} kWh<extra></extra>",
    ))
    theme.base_layout(fig, "kWh / day")
    fig.update_layout(height=320, showlegend=False)
    return fig


def day_component_breakdown_chart(history: tuple[HistoricalHourPoint, ...], day: str) -> go.Figure:
    points = [point for point in history if point.timestamp[:10] == day]
    series: dict[str, list[float]] = defaultdict(lambda: [0.0] * len(points))
    for index, point in enumerate(points):
        for component in point.components:
            series[theme.bucket_label(component.component)][index] += component.kwh
    colors = theme.component_color_map()
    order = [theme.COMPONENT_LABELS[item] for item in theme.COMPONENT_COLOR_ORDER] + [theme.OTHER_LABEL]
    fig = go.Figure()
    for label in order:
        if label in series and any(value > 0 for value in series[label]):
            fig.add_bar(x=[point.timestamp[11:16] for point in points], y=series[label], name=label, marker_color=colors[label])
    fig.update_layout(barmode="stack", height=390, legend=dict(orientation="h", y=-0.28))
    theme.base_layout(fig, "kWh", "Hour")
    return fig


def forecast_energy_chart(bundle: ForecastBundle) -> go.Figure:
    x = [point.timestamp[5:16].replace("T", " ") for point in bundle.points]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=[point.p90_kwh for point in bundle.points], line=dict(width=0), name="P90", hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=x, y=[point.p10_kwh for point in bundle.points], line=dict(width=0), fill="tonexty",
        fillcolor="rgba(42,120,214,0.15)", name="P10–P90 uncertainty", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=x, y=[point.p50_kwh for point in bundle.points], mode="lines",
        line=dict(color=theme.CATEGORICAL[1], width=1.5, dash="dot"), name="P50 ensemble",
    ))
    fig.add_trace(go.Scatter(
        x=x, y=[point.expected_kwh for point in bundle.points], mode="lines",
        line=dict(color=theme.CATEGORICAL[0], width=2.5), name="Expected demand (point forecast)",
    ))
    theme.base_layout(fig, "kWh")
    fig.update_layout(height=340, legend=dict(orientation="h", y=-0.25))
    return fig


def forecast_temperature_chart(bundle: ForecastBundle) -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=[point.timestamp[5:16].replace("T", " ") for point in bundle.points],
        y=[point.outdoor_temp_c for point in bundle.points], mode="lines",
        line=dict(color=theme.CATEGORICAL[1], width=2), name="Outdoor temperature",
    ))
    theme.base_layout(fig, "°C")
    fig.update_layout(height=220, showlegend=False)
    return fig


def peak_probability_chart(bundle: ForecastBundle) -> go.Figure:
    points = sorted(bundle.points, key=lambda point: point.peak_probability, reverse=True)[:12]
    fig = go.Figure(go.Bar(
        x=[point.timestamp[5:16].replace("T", " ") for point in points],
        y=[100 * point.peak_probability for point in points],
        marker_color=[theme.RISK_COLORS[point.peak_risk_label] for point in points],
        customdata=[point.peak_risk_label for point in points],
        hovertemplate="%{x}<br>%{y:.0f}% peak risk — %{customdata}<extra></extra>",
    ))
    theme.base_layout(fig, "Peak probability (%)")
    fig.update_layout(height=330, showlegend=False)
    return fig


def p95_chart(bundle: ForecastBundle) -> go.Figure:
    points = sorted(bundle.points, key=lambda point: point.p95_kwh, reverse=True)[:12]
    fig = go.Figure(go.Bar(
        x=[point.timestamp[5:16].replace("T", " ") for point in points],
        y=[point.p95_kwh for point in points], marker_color=theme.CATEGORICAL[3],
        hovertemplate="%{x}<br>%{y:.2f} kWh P95<extra></extra>",
    ))
    theme.base_layout(fig, "High-demand potential P95 (kWh)")
    fig.update_layout(height=310, showlegend=False)
    return fig


def tariff_chart() -> go.Figure:
    hours = list(range(24))
    prices = [next(price for start, end, price in TARIFF_BANDS_EUR_PER_KWH if start <= hour < end) for hour in hours]
    colors = [theme.CATEGORICAL[0] if price == 0.18 else theme.CATEGORICAL[3] if price == 0.40 else theme.CATEGORICAL[1] for price in prices]
    fig = go.Figure(go.Bar(x=[f"{hour:02d}:00" for hour in hours], y=prices, marker_color=colors))
    theme.base_layout(fig, "EUR / kWh")
    fig.update_layout(height=330, showlegend=False, bargap=0)
    return fig


def flexibility_class_chart(items: tuple[FlexibilityItem, ...]) -> go.Figure:
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[item.flexibility_class.value] += 1
    order = ["fixed", "behavior_driven", "limited", "shiftable"]
    fig = go.Figure(go.Bar(
        x=[theme.FLEXIBILITY_CLASS_LABELS[value] for value in order],
        y=[counts[value] for value in order],
        marker_color=[theme.FLEXIBILITY_CLASS_COLORS[value] for value in order],
    ))
    theme.base_layout(fig, "Components")
    fig.update_layout(height=310, showlegend=False)
    return fig


def optimizer_day_chart(points: tuple[OptimizationHourPoint, ...], day: str) -> go.Figure:
    selected = [point for point in points if point.timestamp[:10] == day]
    x = [point.timestamp[11:16] for point in selected]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=[point.current_load_kwh for point in selected], mode="lines+markers", name="Current schedule", line=dict(color=theme.CATEGORICAL[0])))
    fig.add_trace(go.Scatter(x=x, y=[point.optimized_load_kwh for point in selected], mode="lines+markers", name="Optimized schedule", line=dict(color=theme.CATEGORICAL[2])))
    theme.base_layout(fig, "Household load (kWh)", "Hour")
    fig.update_layout(height=340, legend=dict(orientation="h", y=-0.23))
    return fig


def pv_cost_chart(rows: tuple[PVEconomicsRow, ...]) -> go.Figure:
    x = [f"{row.capacity_kwp:g} kWp" for row in rows]
    fig = go.Figure()
    fig.add_bar(x=x, y=[row.current["annual_net_electricity_cost_eur"] for row in rows], name="Current habits", marker_color=theme.CATEGORICAL[0])
    fig.add_bar(x=x, y=[row.optimized["annual_net_electricity_cost_eur"] for row in rows], name="Optimized habits", marker_color=theme.CATEGORICAL[2])
    fig.update_layout(barmode="group", height=330, legend=dict(orientation="h", y=-0.22))
    theme.base_layout(fig, "Annualized net electricity cost (EUR)")
    return fig


def pv_payback_chart(rows: tuple[PVEconomicsRow, ...]) -> go.Figure:
    x = [f"{row.capacity_kwp:g} kWp" for row in rows]
    fig = go.Figure()
    fig.add_bar(x=x, y=[row.current["simple_payback_years"] for row in rows], name="Current habits", marker_color=theme.CATEGORICAL[0])
    fig.add_bar(x=x, y=[row.optimized["simple_payback_years"] for row in rows], name="Optimized habits", marker_color=theme.CATEGORICAL[2])
    fig.update_layout(barmode="group", height=330, legend=dict(orientation="h", y=-0.22))
    theme.base_layout(fig, "SIMPLE PAYBACK (years)")
    return fig
