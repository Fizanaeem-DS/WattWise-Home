"""Shared visual theme retained from Ivana's WattWise app shell."""

from __future__ import annotations

from hackowatt_stage11.models import LoadComponent

SURFACE = "#fcfcfb"
PAGE_PLANE = "#f9f9f7"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
AXIS_BASELINE = "#c3c2b7"
DELTA_UP_GOOD_TEXT = "#006300"

CATEGORICAL = [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
    "#e87ba4", "#008300", "#4a3aa7", "#e34948",
]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}

COMPONENT_COLOR_ORDER = [
    LoadComponent.HVAC, LoadComponent.EV1, LoadComponent.EV2,
    LoadComponent.COOKING, LoadComponent.POOL_HEATING,
    LoadComponent.SAUNA, LoadComponent.DISHWASHER,
]
OTHER_LABEL = "Other (fridge, pool pump, washer/dryer, lighting, base load...)"
COMPONENT_LABELS = {
    LoadComponent.HVAC: "HVAC (heating/cooling)",
    LoadComponent.FRIDGE_FREEZER: "Fridge & freezer",
    LoadComponent.POOL_CIRCULATION: "Pool circulation",
    LoadComponent.POOL_HEATING: "Pool heating",
    LoadComponent.SAUNA: "Sauna",
    LoadComponent.EV1: "EV 1 charging",
    LoadComponent.EV2: "EV 2 charging",
    LoadComponent.COOKING: "Cooking",
    LoadComponent.DISHWASHER: "Dishwasher",
    LoadComponent.WASHER: "Washer",
    LoadComponent.DRYER: "Dryer",
    LoadComponent.TV_COMPUTER: "TV & computers",
    LoadComponent.LIGHTING_INTERIOR: "Interior lighting",
    LoadComponent.LIGHTING_EXTERIOR: "Exterior/security lighting",
    LoadComponent.SMART_HOME_BASE: "Smart-home base load",
    LoadComponent.PHONE_TABLET: "Phone & tablet charging",
}
FLEXIBILITY_CLASS_LABELS = {
    "fixed": "A — Fixed",
    "behavior_driven": "B — Behavioral / not optimized",
    "limited": "C — Limited flexibility",
    "shiftable": "D — Shiftable",
}
FLEXIBILITY_CLASS_COLORS = {
    "fixed": CATEGORICAL[0], "behavior_driven": CATEGORICAL[1],
    "limited": CATEGORICAL[2], "shiftable": CATEGORICAL[3],
}
RISK_COLORS = {"LOW": CATEGORICAL[2], "MEDIUM": CATEGORICAL[3], "HIGH": STATUS["critical"]}


def component_color_map() -> dict[str, str]:
    mapping = {COMPONENT_LABELS[item]: CATEGORICAL[index] for index, item in enumerate(COMPONENT_COLOR_ORDER)}
    mapping[OTHER_LABEL] = CATEGORICAL[7]
    return mapping


def bucket_label(component: LoadComponent) -> str:
    return COMPONENT_LABELS[component] if component in COMPONENT_COLOR_ORDER else OTHER_LABEL


def base_layout(fig, y_title: str = "", x_title: str = "") -> None:
    fig.update_layout(
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=INK_SECONDARY, family="system-ui, -apple-system, Segoe UI, sans-serif"),
        legend=dict(bgcolor=SURFACE, bordercolor=GRIDLINE, borderwidth=1),
        margin=dict(l=10, r=10, t=35, b=10), hovermode="x unified",
    )
    fig.update_xaxes(title=x_title, gridcolor=GRIDLINE, linecolor=AXIS_BASELINE, tickfont=dict(color=INK_MUTED))
    fig.update_yaxes(title=y_title, gridcolor=GRIDLINE, linecolor=AXIS_BASELINE, tickfont=dict(color=INK_MUTED), rangemode="tozero")
