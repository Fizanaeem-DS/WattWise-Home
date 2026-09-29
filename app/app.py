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
st.sidebar.success("Forecast → Decide → Reschedule → Save")
st.sidebar.caption("Europe/Madrid · energy in kWh per hourly interval · currency EUR")


if page == "Home":
    forecast = data.forecasts[Horizon.H24]
    risk_hour = max(forecast.points, key=lambda point: point.peak_probability)
    stage9 = data.optimization.summary["aug_sep"]

    st.title("Good evening, Anna & Robert")
    st.caption("Your WattWise energy plan · Barcelona")
    source_badge(
        data.history_provenance,
        "SIMULATED HOUSEHOLD PROFILE",
        "This household profile is scenario-specific and simulated, not measured. Barcelona weather inputs are used.",
    )

    st.markdown("## High energy pressure expected tonight")
    risk_time = datetime.fromisoformat(risk_hour.timestamp)
    st.write(
        f"**{risk_time.strftime('%H:%M')} is the highest-risk hour in the next 24 hours.** "
        "WattWise separates expected demand from the probability of a high-demand event so the household can act before large loads overlap."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Expected energy · next 24h", f"{forecast.total_expected_kwh:.1f} kWh")
    c2.metric("Highest-risk hour", risk_time.strftime("%H:%M"), f"{risk_hour.peak_probability:.0%} peak risk", delta_color="off")
    c3.metric("Peak tariff · 17:00–22:00", "€0.40/kWh")

    st.markdown("### WattWise found a better schedule")
    st.write(
        "Instead of asking Anna & Robert to simply use less electricity, WattWise identifies which "
        "activities can move and reschedules them within their modeled energy, timing, dependency "
        "and comfort constraints."
    )

    o1, o2, o3, o4 = st.columns(4)
    o1.metric(
        "Electricity cost",
        f"€{stage9['optimized_net_electricity_cost_eur']:.0f}",
        f"from €{stage9['current_net_electricity_cost_eur']:.0f}",
        delta_color="inverse",
    )
    o2.metric(
        "Grid import",
        f"{stage9['optimized_grid_import_kwh']:,.0f} kWh",
        f"−{(stage9['current_grid_import_kwh'] - stage9['optimized_grid_import_kwh']) / stage9['current_grid_import_kwh']:.1%}",
    )
    o3.metric(
        "Solar self-use",
        f"{stage9['optimized_pv_self_consumption_kwh']:,.0f} kWh",
        f"+{(stage9['optimized_pv_self_consumption_kwh'] - stage9['current_pv_self_consumption_kwh']) / stage9['current_pv_self_consumption_kwh']:.1%}",
    )
    o4.metric(
        "Maximum hourly load",
        f"{stage9['optimized_maximum_hourly_load_kwh']:.1f} kWh",
        f"−{stage9['peak_reduction_percent']:.1f}%",
    )
    st.caption("61-day modeled evaluation · 5 kWp reference PV · household demand is simulated, not measured.")

    st.markdown("### What WattWise does")
    p1, p2, p3 = st.columns(3)
    p1.markdown("**1 · Anticipate**  \nForecast expected demand and identify hours with elevated peak risk.")
    p2.markdown("**2 · Decide**  \nSeparate fixed services from activities that have safe scheduling flexibility.")
    p3.markdown("**3 · Reschedule**  \nBuild a lower-cost, lower-peak schedule while respecting modeled household requirements.")

    st.markdown("### What’s coming?")
    st.caption("Expected demand and uncertainty for the next 24 hours. P10–P90 describes uncertainty; it is not an exact spike prediction.")
    st.plotly_chart(charts.forecast_energy_chart(forecast), width="stretch")
    st.info(
        "WattWise is a scenario demonstration. Household electricity use is simulated; forecasts are retrospective model outputs; "
        "comfort claims apply only to the modeled constraints."
    )

elif page == "My Energy":
    st.title("My Energy")
    st.caption("See what the home has been using, what is coming next, and when demand pressure is highest.")

    tab_now, tab_forecast, tab_risk = st.tabs(["Energy history", "What’s coming", "Peak risk"])

    with tab_now:
        source_badge(
            data.history_provenance,
            "SIMULATED HOUSEHOLD PROFILE",
            "61-day scenario-specific digital twin for Anna & Robert. Household electricity use is simulated, not measured.",
        )
        days = st.radio("History", [7, 14, 30, 61], index=2, horizontal=True, format_func=lambda value: f"Last {value} days")
        st.plotly_chart(charts.daily_total_chart(data.history, days), width="stretch")
        h1, h2, h3 = st.columns(3)
        h1.metric("61-day energy", f"{sum(point.total_kwh for point in data.history):,.0f} kWh")
        h2.metric("Highest hourly demand", f"{max(point.total_kwh for point in data.history):.1f} kWh")
        h3.metric("Average outdoor temperature", f"{sum(point.outdoor_temp_c for point in data.history) / len(data.history):.1f} °C")
        st.caption("Use the history to understand the simulated household pattern; WattWise uses forecasting and risk separately for forward-looking decisions.")

    with tab_forecast:
        choice = st.radio("Look ahead", ["24h", "72h", "168h"], horizontal=True, key="energy_forecast")
        bundle = data.forecasts[Horizon(choice)]
        highest = max(bundle.points, key=lambda point: point.expected_kwh)
        f1, f2 = st.columns(2)
        f1.metric("Expected energy", f"{bundle.total_expected_kwh:.1f} kWh")
        f2.metric("Highest expected-demand hour", datetime.fromisoformat(highest.timestamp).strftime("%d %b · %H:%M"), f"{highest.expected_kwh:.2f} kWh", delta_color="off")
        st.plotly_chart(charts.forecast_energy_chart(bundle), width="stretch")
        st.caption("Expected demand is the model’s central forecast. The uncertainty band describes a range of plausible demand, not an exact spike prediction.")
        with st.expander("Outdoor temperature"):
            st.plotly_chart(charts.forecast_temperature_chart(bundle), width="stretch")

    with tab_risk:
        choice = st.radio("Risk outlook", ["24h", "72h", "168h"], horizontal=True, key="energy_risk")
        bundle = data.forecasts[Horizon(choice)]
        ordered = sorted(bundle.points, key=lambda point: (point.peak_probability, point.p95_kwh), reverse=True)
        top = ordered[0]
        r1, r2, r3 = st.columns(3)
        r1.metric("Highest-risk hour", datetime.fromisoformat(top.timestamp).strftime("%d %b · %H:%M"))
        r2.metric("Peak probability", f"{top.peak_probability:.0%}", top.peak_risk_label, delta_color="off")
        r3.metric("P95 high-demand potential", f"{top.p95_kwh:.1f} kWh")
        st.plotly_chart(charts.peak_probability_chart(bundle), width="stretch")
        st.markdown("### Why does this hour matter?")
        st.write(top.primary_explanation)
        if top.secondary_explanation:
            st.caption(top.secondary_explanation)
        st.info("Peak probability is a risk signal. It does not claim the exact time or size of a future demand spike.")

elif page == "WattWise Plan":
    st.title("Your WattWise Plan")
    st.caption("Turn the forecast into a household schedule: protect fixed services, respect comfort, and move only activities with usable flexibility.")

    summary = data.optimization.summary["aug_sep"]
    comfort = data.optimization.summary["comfort"]
    events = sorted(data.optimization.shifted_events, key=lambda event: abs(event.shift_hours), reverse=True)

    st.markdown("## A better schedule, not less comfort")
    st.write(
        "WattWise combines the household’s flexibility rules, electricity tariff and modeled solar generation. "
        "Fixed and behavior-driven services stay protected; eligible activities move only inside their modeled constraints."
    )
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Activities rescheduled", str(len(events)))
    p2.metric("Electricity cost", f"€{summary['optimized_net_electricity_cost_eur']:.0f}", f"from €{summary['current_net_electricity_cost_eur']:.0f}", delta_color="inverse")
    p3.metric("Maximum hourly load", f"{summary['optimized_maximum_hourly_load_kwh']:.1f} kWh", f"−{summary['peak_reduction_percent']:.1f}%")
    p4.metric("Grid import", f"{summary['optimized_grid_import_kwh']:,.0f} kWh", f"−{summary['current_grid_import_kwh'] - summary['optimized_grid_import_kwh']:,.0f} kWh")

    st.markdown("### What WattWise can and cannot move")
    flex_cols = st.columns(4)
    flex_copy = [
        ("A · Fixed", "Fridge/freezer, smart-home base and security services stay fixed."),
        ("B · Everyday behavior", "Cooking, entertainment and lighting are forecast but not rescheduled."),
        ("C · Limited flexibility", "HVAC, sauna and pool heating move only inside strict modeled limits."),
        ("D · Shiftable", "EV charging, pool circulation, dishwasher and laundry can move inside their windows."),
    ]
    for col, (title, body) in zip(flex_cols, flex_copy):
        col.markdown(f"**{title}**")
        col.caption(body)

    st.markdown("### See the schedule change")
    days = sorted({point.timestamp[:10] for point in data.optimization.hourly})
    day = st.selectbox("Explore a day", days, index=0)
    st.plotly_chart(charts.optimizer_day_chart(data.optimization.hourly, day), width="stretch")

    st.markdown("### Examples of rescheduled activities")
    for event in events[:6]:
        st.markdown(f"- {schedule_change_sentence(event)}")
    with st.expander("See all rescheduled activities"):
        st.dataframe(pd.DataFrame([{
            "Activity": activity_reference(event),
            "Original start": event.original_start,
            "WattWise start": event.optimized_start,
            "Energy (kWh)": event.energy_kwh,
            "Shift (h)": event.shift_hours,
            "Check": scheduling_check(event.constraint_status),
        } for event in events]), hide_index=True, width="stretch")

    st.markdown("### Why timing matters")
    st.plotly_chart(charts.tariff_chart(), width="stretch")
    st.caption("Tariff used in the modeled comparison: 00:00–06:00 €0.18 · 06:00–17:00 €0.28 · 17:00–22:00 €0.40 · 22:00–00:00 €0.28 per kWh.")
    st.info(
        f"Under the modeled constraints, optimization adds no avoidable occupied-hour comfort violation. "
        f"{comfort['physically_infeasible_occupied_hour_count']} occupied hours were physically outside the reachable comfort band; "
        "this is a model result, not a universal real-world comfort guarantee."
    )
    st.caption("61-day modeled evaluation · 5 kWp reference PV · simulated household profile.")

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
