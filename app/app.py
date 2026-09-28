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
PAGES = [
    "Overview", "Historical Consumption", "Forecast", "Peak Hours", "Tariff",
    "Flexibility", "PV Simulator", "Optimizer",
]
page = st.sidebar.radio("Section", PAGES, label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.success("All pages use the validated WattWise scenario results.")
st.sidebar.caption("Europe/Madrid · energy in kWh per hourly interval · currency EUR")


if page == "Overview":
    st.title("⚡ WattWise Home")
    st.caption(data.household_label)
    source_badge(
        data.history_provenance,
        "SIMULATED HOUSEHOLD PROFILE",
        "Scenario-specific digital twin for Anna & Robert, built with Barcelona weather inputs. Household electricity use is simulated, not measured.",
    )
    st.write(
        "Explore how Anna & Robert’s simulated household profile connects expected demand, "
        "probabilistic peak risk, flexible energy use, optimized scheduling, tariffs, solar "
        "generation and investment economics. Expected demand and peak risk are shown separately."
    )
    forecast = data.forecasts[Horizon.H24]
    risk_hour = max(forecast.points, key=lambda point: point.peak_probability)
    stage9 = data.optimization.summary["aug_sep"]
    reference = next(row for row in data.pv.rows if row.capacity_kwp == 5.0)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("61-day household demand", f"{sum(point.total_kwh for point in data.history):,.1f} kWh")
    c2.metric("24-hour expected demand", f"{forecast.total_expected_kwh:.1f} kWh")
    c3.metric("Highest 24h peak risk", f"{risk_hour.peak_probability:.0%}", risk_hour.peak_risk_label, delta_color="off")
    c4.metric(
        "5 kWp SIMPLE PAYBACK — ANNUALIZED ESTIMATE",
        f"{reference.optimized['simple_payback_years']:.2f} years",
        "optimized habits", delta_color="off",
    )
    st.subheader("Current → optimized, 61-day scenario results")
    o1, o2, o3, o4 = st.columns(4)
    o1.metric("Electricity cost", f"€{stage9['optimized_net_electricity_cost_eur']:.2f}", f"−€{stage9['savings_eur']:.2f}")
    o2.metric("Grid import", f"{stage9['optimized_grid_import_kwh']:,.1f} kWh", f"−{stage9['current_grid_import_kwh'] - stage9['optimized_grid_import_kwh']:,.1f} kWh")
    o3.metric("PV self-consumption", f"{stage9['optimized_pv_self_consumption_kwh']:,.1f} kWh", f"+{stage9['optimized_pv_self_consumption_kwh'] - stage9['current_pv_self_consumption_kwh']:,.1f} kWh")
    o4.metric("Maximum hourly load", f"{stage9['optimized_maximum_hourly_load_kwh']:.2f} kWh", f"−{stage9['peak_reduction_percent']:.1f}%")

elif page == "Historical Consumption":
    st.title("Historical Consumption")
    source_badge(
        data.history_provenance,
        "SIMULATED HOUSEHOLD PROFILE",
        "Scenario-specific digital twin covering 61 days in Barcelona. Household electricity use is simulated, not measured.",
    )
    days = st.radio("Show", [7, 14, 30, 61], index=2, horizontal=True, format_func=lambda value: f"Last {value} days")
    st.plotly_chart(charts.daily_total_chart(data.history, days), width="stretch")
    h1, h2, h3 = st.columns(3)
    h1.metric("Period demand", f"{sum(point.total_kwh for point in data.history):,.2f} kWh")
    h2.metric("Maximum hourly demand", f"{max(point.total_kwh for point in data.history):.2f} kWh")
    h3.metric("Mean outdoor temperature", f"{sum(point.outdoor_temp_c for point in data.history) / len(data.history):.1f} °C")
    st.subheader("Simulated component contribution for one day")
    all_days = sorted({point.timestamp[:10] for point in data.history}, reverse=True)
    selected_day = st.selectbox("Day", all_days, index=0)
    st.plotly_chart(charts.day_component_breakdown_chart(data.history, selected_day), width="stretch")
    st.caption("Component energy comes from the simulated household profile; smaller components are grouped only for display.")

elif page == "Forecast":
    st.title("Forecast")
    choice = st.radio("Forecast period", ["24h", "72h", "168h"], horizontal=True)
    bundle = data.forecasts[Horizon(choice)]
    source_badge(
        bundle.provenance,
        f"MODEL FORECAST — {choice.removesuffix('h')}-hour expected demand",
        "Forecast based on the simulated household profile and Barcelona weather inputs. This is a retrospective evaluation window, not a live household forecast.",
    )
    reference_time = datetime.fromisoformat(bundle.forecast_origin).strftime("%d %b %Y, %H:%M")
    st.caption(
        f"Forecast reference time: {reference_time} Europe/Madrid. Only information available "
        "up to this time is used; later household demand is excluded."
    )
    highest = max(bundle.points, key=lambda point: point.expected_kwh)
    high_risk_count = sum(point.peak_risk_label == "HIGH" for point in bundle.points)
    f1, f2, f3 = st.columns(3)
    f1.metric("Total expected energy", f"{bundle.total_expected_kwh:.1f} kWh")
    f2.metric("Highest expected-demand hour", highest.timestamp[5:16].replace("T", " "), f"{highest.expected_kwh:.2f} kWh", delta_color="off")
    f3.metric("HIGH peak-risk hours", str(high_risk_count))
    st.subheader("Expected demand and uncertainty")
    st.caption("The point forecast is expected demand. P10–P90 and P95 describe uncertainty and high-demand potential; they are not exact spike predictions.")
    st.plotly_chart(charts.forecast_energy_chart(bundle), width="stretch")
    st.subheader("Outdoor temperature")
    st.plotly_chart(charts.forecast_temperature_chart(bundle), width="stretch")

elif page == "Peak Hours":
    st.title("Peak Hours")
    choice = st.radio("Forecast period", ["24h", "72h", "168h"], horizontal=True, key="risk_horizon")
    bundle = data.forecasts[Horizon(choice)]
    source_badge(
        bundle.provenance,
        f"PROBABILISTIC PEAK-RISK OUTLOOK — {choice.removesuffix('h')} hours",
        "Peak-risk probabilities and explanations come from the WattWise forecast model. They indicate high-demand potential, not an exact spike prediction.",
    )
    st.info("Expected demand shows how much electricity is anticipated; peak probability shows the likelihood of a high-demand event. Neither can predict the exact timing or size of an individual demand spike.")
    st.subheader("Highest peak-risk hours")
    st.plotly_chart(charts.peak_probability_chart(bundle), width="stretch")
    st.subheader("High-demand potential")
    st.plotly_chart(charts.p95_chart(bundle), width="stretch")
    ordered = sorted(bundle.points, key=lambda point: (point.peak_probability, point.p95_kwh), reverse=True)[:12]
    st.subheader("Why these hours have higher risk")
    st.dataframe(pd.DataFrame([{
        "Timestamp": point.timestamp,
        "Expected demand (kWh)": point.expected_kwh,
        "Peak probability": point.peak_probability,
        "Risk label": point.peak_risk_label,
        "P95 high-demand potential (kWh)": point.p95_kwh,
        "Primary explanation": point.primary_explanation,
        "Secondary explanation": point.secondary_explanation,
    } for point in ordered]), hide_index=True, width="stretch")

elif page == "Tariff":
    st.title("Tariff")
    st.caption("Electricity tariff used consistently for forecasting, scheduling and financial comparisons.")
    now = datetime.now(TZ)
    st.metric("Current tariff band", f"€{tariff_for_hour(now.hour):.2f}/kWh", now.strftime("%H:%M Europe/Madrid"), delta_color="off")
    st.plotly_chart(charts.tariff_chart(), width="stretch")
    st.write("00:00–06:00 €0.18 · 06:00–17:00 €0.28 · 17:00–22:00 €0.40 · 22:00–00:00 €0.28 per kWh")

elif page == "Flexibility":
    st.title("Flexibility")
    source_badge(
        data.flexibility_provenance,
        "MODELED FLEXIBILITY RULES",
        "Scheduling limits are based on the simulated household events and the defined appliance, vehicle and comfort constraints.",
    )
    st.plotly_chart(charts.flexibility_class_chart(data.flexibility), width="stretch")
    st.caption("A fixed · B behavioral/not optimized · C limited flexibility · D shiftable. Values reflect the simulated events generated for this household scenario.")
    st.dataframe(pd.DataFrame([{
        "Component": theme.COMPONENT_LABELS[item.component],
        "Class": theme.FLEXIBILITY_CLASS_LABELS[item.flexibility_class.value],
        "Scenario event instances": item.actual_event_count,
        "Scenario energy range (kWh)": None if item.actual_energy_min_kwh is None else f"{item.actual_energy_min_kwh:.3f}–{item.actual_energy_max_kwh:.3f}",
        "Scenario duration range (h)": None if item.actual_duration_min_hours is None else f"{item.actual_duration_min_hours:.3f}–{item.actual_duration_max_hours:.3f}",
        "Earliest start": item.earliest_start,
        "Latest start": item.latest_start,
        "Latest completion": item.latest_completion,
        "Comfort band": None if item.comfort_band_min is None else f"{item.comfort_band_min}–{item.comfort_band_max} °C",
        "Rule": FLEXIBILITY_NOTE_DISPLAY.get(item.notes, item.notes),
    } for item in data.flexibility]), hide_index=True, width="stretch")
    st.caption("Energy and runtime ranges reflect the simulated household events used for scheduling.")

elif page == "PV Simulator":
    st.title("PV Simulator")
    source_badge(
        data.pv.provenance,
        "MODELED PV AND ANNUALIZED ECONOMICS",
        "PV production is modeled with PVGIS. Financial results use the 61-day household scenario and are annualized estimates, not measured annual performance.",
    )
    st.warning("ANNUALIZED ESTIMATE — not measured annual household performance")
    st.caption(
        "Annualized from the 61-day August–September scenario. Results assume its demand patterns, "
        "solar-use timing and electricity values are representative of a full year; they are not "
        "measured annual household performance."
    )
    capacity = st.select_slider("Comparison capacity (not a recommendation)", options=[3.0, 5.0, 8.0, 10.0], value=5.0, format_func=lambda value: f"{value:g} kWp")
    row = next(item for item in data.pv.rows if item.capacity_kwp == capacity)
    st.metric("Modeled annual PV production (PVGIS)", f"{row.annual_pv_production_kwh:,.2f} kWh/year")
    st.write(f"Initial investment: **€{row.initial_investment_eur:,.0f}** · Annual operation and maintenance: **€{row.annual_om_eur:,.0f}**")
    left, right = st.columns(2)
    for column, title, metrics in ((left, "A — Current habits + PV", row.current), (right, "B — Optimized habits + PV", row.optimized)):
        column.subheader(title)
        column.metric("PV self-consumed", f"{metrics['annual_pv_self_consumed_kwh']:,.1f} kWh")
        column.metric("PV self-consumption rate", f"{metrics['pv_self_consumption_rate']:.1%}")
        column.metric("Household solar coverage", f"{metrics['household_solar_coverage_rate']:.1%}")
        column.metric("Grid electricity purchased", f"{metrics['annual_grid_imported_kwh']:,.1f} kWh")
        column.metric("PV exported", f"{metrics['annual_pv_exported_kwh']:,.1f} kWh")
        column.metric("Annualized net electricity cost", f"€{metrics['annual_net_electricity_cost_eur']:,.2f}")
        column.metric("Annualized net PV benefit", f"€{metrics['net_annual_pv_benefit_eur']:,.2f}")
        column.metric("SIMPLE PAYBACK", f"{metrics['simple_payback_years']:.2f} years")
    st.subheader("PV capacity comparison")
    st.plotly_chart(charts.pv_cost_chart(data.pv.rows), width="stretch")
    st.plotly_chart(charts.pv_payback_chart(data.pv.rows), width="stretch")
    decomposition = next(item for item in data.pv.effect_decomposition["by_capacity"] if float(item["capacity_kwp"]) == capacity)
    st.subheader("Where the savings come from")
    d1, d2, d3 = st.columns(3)
    d1.metric("Scheduling benefit without PV", f"€{decomposition['behavioral_optimization_effect_no_pv_eur']:,.2f}/year")
    d2.metric("PV benefit with optimized scheduling", f"€{decomposition['pv_effect_optimized_habits_net_after_om_eur']:,.2f}/year")
    d3.metric("Combined scheduling + PV benefit", f"€{decomposition['combined_current_no_pv_to_optimized_pv_net_after_om_eur']:,.2f}/year")
    st.caption(
        "Behavioral savings are kept separate from the PV investment benefit. PV production is "
        "modeled with PVGIS, not measured on this roof; no battery is modeled. "
        "SIMPLE PAYBACK excludes NPV, financing, degradation, inflation, subsidies, and taxes."
    )

elif page == "Optimizer":
    st.title("Current vs. Optimized Schedule")
    source_badge(
        data.optimization.provenance,
        "MODELED SCHEDULING RESULTS",
        "Current and optimized schedules use the simulated household profile, tariff, modeled PV and defined flexibility constraints.",
    )
    st.caption("These are completed scenario results; changing the inspected day does not rerun the optimization.")
    summary = data.optimization.summary["aug_sep"]
    comfort = data.optimization.summary["comfort"]
    st.info(
        "Under the modeled constraints, flexible services are preserved and the optimized schedule "
        "adds no avoidable comfort violation during occupied hours. The model identified "
        f"{comfort['physically_infeasible_occupied_hour_count']} occupied hours where the comfort band "
        "was physically unreachable and retained only the minimum unavoidable violation. This is not "
        "a universal real-world comfort guarantee."
    )
    current, optimized = st.columns(2)
    current.subheader("CURRENT SCHEDULE")
    current.metric("Household load", f"{summary['current_total_load_kwh']:,.1f} kWh")
    current.metric("Grid import", f"{summary['current_grid_import_kwh']:,.1f} kWh")
    current.metric("PV self-consumption", f"{summary['current_pv_self_consumption_kwh']:,.1f} kWh")
    current.metric("PV export", f"{summary['current_exported_pv_kwh']:,.1f} kWh")
    current.metric("Electricity cost", f"€{summary['current_net_electricity_cost_eur']:,.2f}")
    current.metric("Maximum hourly load", f"{summary['current_maximum_hourly_load_kwh']:.2f} kWh")
    optimized.subheader("OPTIMIZED SCHEDULE")
    optimized.metric("Household load", f"{summary['optimized_total_load_kwh']:,.1f} kWh")
    optimized.metric("Grid import", f"{summary['optimized_grid_import_kwh']:,.1f} kWh")
    optimized.metric("PV self-consumption", f"{summary['optimized_pv_self_consumption_kwh']:,.1f} kWh")
    optimized.metric("PV export", f"{summary['optimized_exported_pv_kwh']:,.1f} kWh")
    optimized.metric("Electricity cost", f"€{summary['optimized_net_electricity_cost_eur']:,.2f}", f"€{summary['savings_eur']:.2f} saved")
    optimized.metric("Maximum hourly load", f"{summary['optimized_maximum_hourly_load_kwh']:.2f} kWh", f"−{summary['peak_reduction_percent']:.1f}%")
    days = sorted({point.timestamp[:10] for point in data.optimization.hourly})
    day = st.selectbox("Explore a day", days, index=0)
    st.plotly_chart(charts.optimizer_day_chart(data.optimization.hourly, day), width="stretch")
    st.subheader("Rescheduled household activities")
    events = sorted(data.optimization.shifted_events, key=lambda event: abs(event.shift_hours), reverse=True)
    st.caption(f"{len(events)} activities were rescheduled while preserving their modeled duration, power, energy, ordering, availability and comfort requirements.")
    for event in events[:8]:
        st.markdown(f"- {schedule_change_sentence(event)}")
    st.dataframe(pd.DataFrame([{
        "Activity reference": activity_reference(event),
        "Component": theme.COMPONENT_LABELS[event.component],
        "Original start": event.original_start,
        "Optimized start": event.optimized_start,
        "Energy (kWh)": event.energy_kwh,
        "Duration (h)": event.duration_hours,
        "Shift (h)": event.shift_hours,
        "Scheduling check": scheduling_check(event.constraint_status),
    } for event in events]), hide_index=True, width="stretch")
