"""WattWise Home — Ivana's preserved Streamlit shell with real Stage 11 data."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP_DIR)
for path in (ROOT, os.path.join(ROOT, "src"), APP_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import pandas as pd
import streamlit as st

import charts
import theme
from data_source import get_data
from suggestions import schedule_change_sentence
from hackowatt_stage11.models import Horizon, Provenance, TARIFF_BANDS_EUR_PER_KWH

TZ = ZoneInfo("Europe/Madrid")
st.set_page_config(page_title="WattWise Home", page_icon="⚡", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1240px;}
[data-testid="stSidebar"] {background: #f7f8f5; border-right: 1px solid #e7e9e3;}
[data-testid="stMetric"] {background: white; border: 1px solid #e8ebe5; border-radius: 16px; padding: 16px 18px; box-shadow: 0 5px 18px rgba(25,40,30,.045);}
[data-testid="stMetricLabel"] {font-size: .82rem;}
[data-testid="stMetricValue"] {font-weight: 720;}
div[data-testid="stAlert"] {border-radius: 14px;}
.watt-hero {background: linear-gradient(135deg,#10281f 0%,#174c39 100%); color:white; border-radius:24px; padding:28px 30px; margin:12px 0 22px 0; box-shadow:0 14px 35px rgba(16,40,31,.16);}
.watt-eyebrow {font-size:.76rem;letter-spacing:.12em;text-transform:uppercase;font-weight:700;color:#b9e6d0;margin-bottom:10px;}
.watt-hero h2 {font-size:2rem;line-height:1.15;margin:0 0 8px;color:white;}
.watt-hero p {color:#dcebe4;margin:0;font-size:1.02rem;}
.plan-card {background:#f3f8f5;border:1px solid #d9e8df;border-radius:18px;padding:18px 20px;height:100%;}
.plan-label {font-size:.76rem;text-transform:uppercase;letter-spacing:.08em;color:#557264;font-weight:700;}
.plan-title {font-size:1.02rem;font-weight:700;color:#173a2c;margin:5px 0;}
.plan-time {font-size:1.35rem;font-weight:750;color:#0f5d3d;}
.section-kicker {color:#0f6b46;font-weight:700;font-size:.82rem;text-transform:uppercase;letter-spacing:.08em;margin-top:10px;}
.small-disclosure {color:#777;font-size:.82rem;margin-top:12px;}
</style>
""", unsafe_allow_html=True)


def source_badge(provenance: Provenance, label: str, description: str) -> None:
    st.markdown(
        f"""<div style="background:{theme.STATUS['good']};color:#fff;padding:6px 12px;
        border-radius:6px;display:inline-block;font-size:.85rem;font-weight:600;margin-bottom:.6rem;">
        ✅ {label}</div>""",
        unsafe_allow_html=True,
    )
    st.caption(description)


FLEXIBILITY_NOTE_DISPLAY = {
    "Continuous; optimizer may not change it.": "Continuous fixed load; not rescheduled.",
    "Security/exterior lighting; optimizer may not change it.": "Security and exterior lighting remain fixed.",
    "Morning and dinner cooking; forecast, never reschedule.": "Morning and dinner cooking are included in demand forecasts but not rescheduled.",
    "Behavioral session; never reschedule.": "Behavior-driven activity; not rescheduled.",
    "Behavior-driven; never reschedule.": "Behavior-driven activity; not rescheduled.",
    "Occupancy/darkness driven; never reschedule.": "Driven by occupancy and darkness; not rescheduled.",
    "Display envelope only; production has separate heating/cooling bands.": "Summary only: heating and cooling use separate modeled comfort bands.",
    "Representative runtime only; actual start +/-1h, absolute START window 18:00-22:30.": "Preferred start ±1 hour; allowed start times are limited to 18:00–22:30.",
    "Approved same-day production rule; actual Stage 3 service quantity is authoritative.": "Scheduled on the same day while preserving each simulated event’s required energy, duration and power.",
    "Actual home interval, energy and next departure are per event.": "Each charging event uses its own home interval, energy requirement and next departure.",
    "Independent of EV1; actual values are per event.": "EV 2 is scheduled independently using its own home interval, energy requirement and next departure.",
    "Representative normal-day runtime only; actual normal/AWAY runtime is authoritative.": "Runtime follows each simulated day’s normal or away-day requirement.",
    "No fixed earliest clock time; actual occurrence establishes availability.": "Scheduling begins from the simulated occurrence; no fixed clock-time start is imposed.",
    "Must follow paired washer; actual dependency and quantities are authoritative.": "Scheduled after its paired washer while preserving both activities’ simulated requirements.",
}


def activity_reference(event) -> str:
    suffix = event.event_id.rsplit("_", 1)[-1]
    number = str(int(suffix)) if suffix.isdigit() else suffix.replace("_", " ").title()
    return f"{theme.COMPONENT_LABELS[event.component]} {number}"


def scheduling_check(status: str) -> str:
    return "All requirements met" if status == "satisfied" else status.replace("_", " ").title()


def tariff_for_hour(hour: int) -> float:
    return next(price for start, end, price in TARIFF_BANDS_EUR_PER_KWH if start <= hour < end)


data = get_data()
if data.has_any_mock():
    st.error("WattWise could not verify the required scenario data, so this page cannot be displayed.")
    st.stop()

st.sidebar.title("⚡ WattWise Home")
st.sidebar.caption(data.household_label)
st.sidebar.caption("Scenario 3 — “Luxury Under Control”")
PAGES = ["Home", "My Energy", "WattWise Plan", "Solar"]
page = st.sidebar.radio("Navigate", PAGES, label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.caption("Europe/Madrid · energy in kWh per hourly interval · currency EUR")


if page == "Home":
    forecast = data.forecasts[Horizon.H24]
    risk_hour = max(forecast.points, key=lambda point: point.peak_probability)
    risk_time = datetime.fromisoformat(risk_hour.timestamp)
    stage9 = data.optimization.summary["aug_sep"]
    home_events = sorted(data.optimization.shifted_events, key=lambda event: abs(event.shift_hours), reverse=True)

    st.caption("WATTWISE HOME · BARCELONA")
    st.title("Good evening, Anna & Robert")
    st.markdown(
        f"""<div class="watt-hero">
        <div class="watt-eyebrow">Tonight’s energy outlook</div>
        <h2>Energy pressure is highest around {risk_time.strftime('%H:%M')}</h2>
        <p>Several high-power activities may overlap while electricity is in its most expensive evening period. WattWise has already found a lower-pressure schedule.</p>
        </div>""",
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("NEXT 24 HOURS", f"{forecast.total_expected_kwh:.1f} kWh", "expected energy", delta_color="off")
    c2.metric("PEAK-RISK SIGNAL", f"{risk_hour.peak_probability:.0%}", f"highest at {risk_time.strftime('%H:%M')}", delta_color="off")
    c3.metric("EVENING TARIFF", "€0.40/kWh", "17:00–22:00", delta_color="off")

    st.markdown('<div class="section-kicker">Your WattWise plan</div>', unsafe_allow_html=True)
    st.markdown("## Your plan is ready")
    st.caption("WattWise moves only eligible activities and keeps modeled energy, timing, dependency and comfort requirements intact.")

    examples = home_events[:3]
    cols = st.columns(3)
    for col, event in zip(cols, examples):
        original = datetime.fromisoformat(event.original_start)
        optimized = datetime.fromisoformat(event.optimized_start)
        label = theme.COMPONENT_LABELS[event.component]
        with col:
            st.markdown(
                f"""<div class="plan-card">
                <div class="plan-label">{label}</div>
                <div class="plan-title">Better time found</div>
                <div class="plan-time">{original.strftime('%H:%M')} → {optimized.strftime('%H:%M')}</div>
                <div style="color:#617168;font-size:.85rem;margin-top:6px;">{event.energy_kwh:.1f} kWh service preserved</div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.caption(f"3 examples shown · {len(home_events)} activities rescheduled across the 61-day modeled evaluation · full schedule in **WattWise Plan**")

    st.markdown('<div class="section-kicker">Modeled impact</div>', unsafe_allow_html=True)
    st.markdown("## Same household services. Smarter timing.")
    o1, o2, o3, o4 = st.columns(4)
    savings_pct = stage9["savings_eur"] / stage9["current_net_electricity_cost_eur"]
    grid_pct = (stage9["current_grid_import_kwh"] - stage9["optimized_grid_import_kwh"]) / stage9["current_grid_import_kwh"]
    solar_pct = (stage9["optimized_pv_self_consumption_kwh"] - stage9["current_pv_self_consumption_kwh"]) / stage9["current_pv_self_consumption_kwh"]
    o1.metric("ELECTRICITY COST", f"€{stage9['optimized_net_electricity_cost_eur']:.0f}", f"↓ {savings_pct:.0%} from €{stage9['current_net_electricity_cost_eur']:.0f}", delta_color="off")
    o2.metric("MAX HOURLY LOAD", f"{stage9['optimized_maximum_hourly_load_kwh']:.1f} kWh", f"↓ {stage9['peak_reduction_percent']:.1f}%", delta_color="off")
    o3.metric("GRID IMPORT", f"{stage9['optimized_grid_import_kwh']:,.0f} kWh", f"↓ {grid_pct:.1%}", delta_color="off")
    o4.metric("SOLAR SELF-USE", f"{stage9['optimized_pv_self_consumption_kwh']:,.0f} kWh", f"↑ {solar_pct:.1%}", delta_color="off")
    st.caption("61-day modeled evaluation · 5 kWp reference PV.")

    st.markdown('<div class="section-kicker">Why WattWise</div>', unsafe_allow_html=True)
    st.markdown("## From warning to action")
    a1, a2, a3 = st.columns(3)
    a1.markdown("**01 · See it coming**")
    a1.caption("Forecast expected demand and identify hours where high demand is more likely.")
    a2.markdown("**02 · Know what can move**")
    a2.caption("Protect fixed services and everyday behavior; use only genuine household flexibility.")
    a3.markdown("**03 · Get a better schedule**")
    a3.caption("Reschedule eligible activities around tariff, solar and modeled household constraints.")

    with st.expander("See the next 24-hour forecast"):
        st.plotly_chart(charts.forecast_energy_chart(forecast), width="stretch")
        st.caption("Expected demand and uncertainty are shown separately; the range is not an exact spike prediction.")

    st.markdown(
        '<div class="small-disclosure">Demo disclosure: household electricity use is scenario-specific and simulated, not measured. '
        'Forecasts are retrospective model outputs; comfort claims apply only to the modeled constraints. Barcelona weather inputs are used.</div>',
        unsafe_allow_html=True,
    )

elif page == "My Energy":
    st.caption("MY ENERGY · UNDERSTAND YOUR HOME")
    st.title("My Energy")
    st.caption("Your household pattern, what is coming next, and the hours that deserve attention.")

    tab_now, tab_forecast, tab_risk = st.tabs(["Energy history", "What’s coming", "Peak risk"])

    with tab_now:
        st.markdown('<div class="section-kicker">Your energy pattern</div>', unsafe_allow_html=True)
        st.markdown("## See how your home uses energy")
        st.caption("Explore the simulated household profile across the last 7, 14, 30 or 61 days.")
        days = st.radio("History", [7, 14, 30, 61], index=2, horizontal=True, format_func=lambda value: f"Last {value} days")
        st.plotly_chart(charts.daily_total_chart(data.history, days), width="stretch")
        h1, h2, h3 = st.columns(3)
        h1.metric("61-DAY ENERGY", f"{sum(point.total_kwh for point in data.history):,.0f} kWh")
        h2.metric("HIGHEST HOURLY DEMAND", f"{max(point.total_kwh for point in data.history):.1f} kWh")
        h3.metric("AVERAGE OUTDOOR TEMP.", f"{sum(point.outdoor_temp_c for point in data.history) / len(data.history):.1f} °C")
        st.markdown('<div class="small-disclosure">Demo disclosure: this 61-day household electricity profile is scenario-specific and simulated, not measured.</div>', unsafe_allow_html=True)

    with tab_forecast:
        st.markdown('<div class="section-kicker">Look ahead</div>', unsafe_allow_html=True)
        st.markdown("## What your home is likely to need")
        st.caption("Choose how far ahead you want to look. WattWise shows expected demand separately from uncertainty.")
        choice = st.radio("Forecast period", ["24h", "72h", "168h"], horizontal=True, key="energy_forecast")
        bundle = data.forecasts[Horizon(choice)]
        highest = max(bundle.points, key=lambda point: point.expected_kwh)
        f1, f2 = st.columns(2)
        f1.metric("EXPECTED ENERGY", f"{bundle.total_expected_kwh:.1f} kWh", f"next {choice}", delta_color="off")
        f2.metric("BUSIEST EXPECTED HOUR", datetime.fromisoformat(highest.timestamp).strftime("%d %b · %H:%M"), f"{highest.expected_kwh:.2f} kWh expected", delta_color="off")
        st.plotly_chart(charts.forecast_energy_chart(bundle), width="stretch")
        st.caption("The central line is expected demand. The surrounding range shows plausible uncertainty; it is not an exact spike prediction.")
        with st.expander("See outdoor temperature forecast"):
            st.plotly_chart(charts.forecast_temperature_chart(bundle), width="stretch")
        st.markdown('<div class="small-disclosure">Forecasts shown here are retrospective model outputs for the scenario demonstration.</div>', unsafe_allow_html=True)

    with tab_risk:
        st.markdown('<div class="section-kicker">When to pay attention</div>', unsafe_allow_html=True)
        st.markdown("## Find the hours with higher demand risk")
        st.caption("Expected demand and peak risk answer different questions. This view highlights when unusually high household demand is more likely.")
        choice = st.radio("Risk period", ["24h", "72h", "168h"], horizontal=True, key="energy_risk")
        bundle = data.forecasts[Horizon(choice)]
        ordered = sorted(bundle.points, key=lambda point: (point.peak_probability, point.p95_kwh), reverse=True)
        top = ordered[0]
        r1, r2, r3 = st.columns(3)
        r1.metric("HIGHEST-RISK HOUR", datetime.fromisoformat(top.timestamp).strftime("%d %b · %H:%M"))
        r2.metric("PEAK-RISK SIGNAL", f"{top.peak_probability:.0%}", top.peak_risk_label, delta_color="off")
        r3.metric("HIGH-DEMAND RANGE", f"{top.p95_kwh:.1f} kWh", "P95 model range", delta_color="off")
        st.plotly_chart(charts.peak_probability_chart(bundle), width="stretch")
        st.markdown("### Why this hour deserves attention")
        st.write(top.primary_explanation)
        if top.secondary_explanation:
            st.caption(top.secondary_explanation)
        st.info("The peak-risk signal helps prioritize attention. It does not claim the exact time or size of a future demand spike.")
        st.markdown('<div class="small-disclosure">P95 is retained as the model’s high-demand uncertainty range; household electricity use is simulated.</div>', unsafe_allow_html=True)

elif page == "WattWise Plan":
    summary = data.optimization.summary["aug_sep"]
    comfort = data.optimization.summary["comfort"]
    events = sorted(data.optimization.shifted_events, key=lambda event: abs(event.shift_hours), reverse=True)

    st.caption("WATTWISE PLAN · YOUR ACTIONABLE SCHEDULE")
    st.title("Your WattWise Plan")
    st.markdown(
        """<div class="watt-hero">
        <div class="watt-eyebrow">Your optimized energy plan</div>
        <h2>Keep the household services. Change the timing.</h2>
        <p>WattWise finds where flexible activities can move around expensive hours and solar availability, while respecting the modeled household rules.</p>
        </div>""",
        unsafe_allow_html=True,
    )

    p1, p2, p3, p4 = st.columns(4)
    savings_pct = summary["savings_eur"] / summary["current_net_electricity_cost_eur"]
    grid_pct = (summary["current_grid_import_kwh"] - summary["optimized_grid_import_kwh"]) / summary["current_grid_import_kwh"]
    p1.metric("ACTIVITIES RESCHEDULED", str(len(events)), "modeled evaluation", delta_color="off")
    p2.metric("ELECTRICITY COST", f"€{summary['optimized_net_electricity_cost_eur']:.0f}", f"↓ {savings_pct:.0%} from €{summary['current_net_electricity_cost_eur']:.0f}", delta_color="off")
    p3.metric("MAX HOURLY LOAD", f"{summary['optimized_maximum_hourly_load_kwh']:.1f} kWh", f"↓ {summary['peak_reduction_percent']:.1f}%", delta_color="off")
    p4.metric("GRID IMPORT", f"{summary['optimized_grid_import_kwh']:,.0f} kWh", f"↓ {grid_pct:.1%}", delta_color="off")

    st.markdown('<div class="section-kicker">What changed</div>', unsafe_allow_html=True)
    st.markdown("## A few activities WattWise moved")
    st.caption("These are real examples from the modeled optimizer output — not generic energy-saving tips.")
    top_events = events[:3]
    cols = st.columns(3)
    for col, event in zip(cols, top_events):
        original = datetime.fromisoformat(event.original_start)
        optimized = datetime.fromisoformat(event.optimized_start)
        label = theme.COMPONENT_LABELS[event.component]
        with col:
            st.markdown(
                f"""<div class="plan-card">
                <div class="plan-label">{label}</div>
                <div class="plan-title">WattWise schedule</div>
                <div class="plan-time">{original.strftime('%H:%M')} → {optimized.strftime('%H:%M')}</div>
                <div style="color:#617168;font-size:.85rem;margin-top:6px;">{event.energy_kwh:.1f} kWh service preserved</div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.markdown('<div class="section-kicker">Explore the schedule</div>', unsafe_allow_html=True)
    st.markdown("## See current vs WattWise timing")
    days = sorted({point.timestamp[:10] for point in data.optimization.hourly})
    day = st.selectbox("Choose a day", days, index=0)
    st.plotly_chart(charts.optimizer_day_chart(data.optimization.hourly, day), width="stretch")
    st.caption("The comparison uses the same tariff and PV accounting for current and optimized schedules.")

    with st.expander(f"See all {len(events)} rescheduled activities"):
        st.dataframe(pd.DataFrame([{
            "Activity": activity_reference(event),
            "Original": event.original_start,
            "WattWise": event.optimized_start,
            "Energy (kWh)": event.energy_kwh,
            "Shift (h)": event.shift_hours,
            "Status": scheduling_check(event.constraint_status),
        } for event in events]), hide_index=True, width="stretch")

    st.markdown('<div class="section-kicker">Household rules</div>', unsafe_allow_html=True)
    st.markdown("## WattWise does not move everything")
    st.caption("Every household activity is treated according to how much real scheduling freedom it has in the scenario.")
    flex_cols = st.columns(4)
    flex_copy = [
        ("A · Always on", "Fridge/freezer, smart-home base and security services stay fixed."),
        ("B · Your behavior", "Cooking, entertainment and lighting are forecast but left to the household."),
        ("C · Comfort-limited", "HVAC, sauna and pool heating move only inside strict modeled limits."),
        ("D · Flexible", "EV charging, pool circulation, dishwasher and laundry can move inside their allowed windows."),
    ]
    for col, (title, body) in zip(flex_cols, flex_copy):
        with col:
            st.markdown(f"""<div class="plan-card"><div class="plan-label">{title}</div><div style="color:#41554b;font-size:.9rem;margin-top:8px;">{body}</div></div>""", unsafe_allow_html=True)

    st.markdown('<div class="section-kicker">Why these times</div>', unsafe_allow_html=True)
    st.markdown("## Electricity costs more in the evening")
    st.plotly_chart(charts.tariff_chart(), width="stretch")
    st.caption("Modeled tariff: 00:00–06:00 €0.18 · 06:00–17:00 €0.28 · 17:00–22:00 €0.40 · 22:00–00:00 €0.28 per kWh.")

    with st.expander("Modeled comfort and optimization limits"):
        st.write(
            f"Under the modeled constraints, optimization adds no avoidable occupied-hour comfort violation. "
            f"{comfort['physically_infeasible_occupied_hour_count']} occupied hours were physically outside the reachable comfort band. "
            "This is a modeled result, not a universal real-world comfort guarantee."
        )
        st.caption("The 61-day optimization comparison uses a 5 kWp reference PV system and a simulated household profile.")

elif page == "Solar":
    st.title("Solar")
    st.caption("Explore how different PV capacities interact with Anna & Robert’s simulated household schedule.")
    source_badge(
        data.pv.provenance,
        "MODELED SOLAR + ANNUALIZED ESTIMATE",
        "PV production is modeled with PVGIS. Household financial results are annualized from the 61-day scenario and are not measured annual performance.",
    )

    capacity = st.select_slider(
        "Compare a PV capacity",
        options=[3.0, 5.0, 8.0, 10.0],
        value=5.0,
        format_func=lambda value: f"{value:g} kWp",
    )
    row = next(item for item in data.pv.rows if item.capacity_kwp == capacity)

    st.markdown(f"## What would {capacity:g} kWp change?")
    s1, s2, s3 = st.columns(3)
    s1.metric("Modeled PV production", f"{row.annual_pv_production_kwh:,.0f} kWh/year")
    s2.metric("Initial investment", f"€{row.initial_investment_eur:,.0f}")
    s3.metric("Annual O&M", f"€{row.annual_om_eur:,.0f}")

    left, right = st.columns(2)
    left.markdown("### Current habits + solar")
    right.markdown("### With WattWise scheduling")
    left.metric("Solar used at home", f"{row.current['pv_self_consumption_rate']:.1%}")
    right.metric("Solar used at home", f"{row.optimized['pv_self_consumption_rate']:.1%}")
    left.metric("Grid electricity", f"{row.current['annual_grid_imported_kwh']:,.0f} kWh/year")
    right.metric("Grid electricity", f"{row.optimized['annual_grid_imported_kwh']:,.0f} kWh/year")
    left.metric("Annualized net electricity cost", f"€{row.current['annual_net_electricity_cost_eur']:,.0f}/year")
    right.metric("Annualized net electricity cost", f"€{row.optimized['annual_net_electricity_cost_eur']:,.0f}/year")
    left.metric("SIMPLE PAYBACK", f"{row.current['simple_payback_years']:.2f} years")
    right.metric("SIMPLE PAYBACK", f"{row.optimized['simple_payback_years']:.2f} years")

    st.markdown("### Compare capacities")
    st.plotly_chart(charts.pv_cost_chart(data.pv.rows), width="stretch")
    st.plotly_chart(charts.pv_payback_chart(data.pv.rows), width="stretch")

    decomposition = next(item for item in data.pv.effect_decomposition["by_capacity"] if float(item["capacity_kwp"]) == capacity)
    st.markdown("### Where the value comes from")
    d1, d2, d3 = st.columns(3)
    d1.metric("Scheduling without solar", f"€{decomposition['behavioral_optimization_effect_no_pv_eur']:,.0f}/year")
    d2.metric("Solar benefit with WattWise", f"€{decomposition['pv_effect_optimized_habits_net_after_om_eur']:,.0f}/year")
    d3.metric("Combined modeled benefit", f"€{decomposition['combined_current_no_pv_to_optimized_pv_net_after_om_eur']:,.0f}/year")

    st.warning("ANNUALIZED ESTIMATE · Capacity options are comparisons, not PV sizing recommendations.")
    st.caption(
        "Annualized from the 61-day August–September simulated household profile. PV production is modeled with PVGIS, not measured on this roof. "
        "SIMPLE PAYBACK excludes financing, discounting, degradation, inflation, subsidies and taxes. No battery is modeled."
    )
