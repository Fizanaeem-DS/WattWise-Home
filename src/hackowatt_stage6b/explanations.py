"""Fixed display labels, tariffs, and probabilistic explanation rules."""

from __future__ import annotations

from typing import Any


ALLOWED_EXPLANATION_INPUTS = {
    "hour",
    "behavioral_block",
    "is_weekend",
    "temperature_2m",
    "point_forecast_kwh",
    "peak_probability",
    "peak_risk_label",
    "tariff_period",
    "tariff_eur_per_kwh",
}

FORBIDDEN_EXPLANATION_INPUTS = {
    "actual_household_kwh",
    "actual_high_demand",
    "away",
    "occupancy_state",
    "guest_event",
    "hvac_mode",
    "indoor_temperature_c",
    "ev1_charging_kwh",
    "ev2_charging_kwh",
    "sauna_kwh",
    "pool_heating_kwh",
    "event_ledger",
}


def risk_label(probability: float) -> str:
    if probability < 0.20:
        return "LOW"
    if probability < 0.40:
        return "MEDIUM"
    return "HIGH"


def tariff(hour: int) -> tuple[float, str]:
    if 0 <= hour < 6:
        return 0.18, "OFF_PEAK_00_06"
    if 6 <= hour < 17:
        return 0.28, "STANDARD_06_17"
    if 17 <= hour < 22:
        return 0.40, "PEAK_17_22"
    return 0.28, "STANDARD_22_24"


def explanations(context: dict[str, Any]) -> tuple[str, str]:
    if set(context) != ALLOWED_EXPLANATION_INPUTS:
        missing = sorted(ALLOWED_EXPLANATION_INPUTS - set(context))
        extra = sorted(set(context) - ALLOWED_EXPLANATION_INPUTS)
        raise ValueError(f"Explanation context mismatch; missing={missing}, extra={extra}")

    hour = int(context["hour"])
    probability = float(context["peak_probability"])
    temperature = float(context["temperature_2m"])
    candidates: list[str] = []

    if 18 <= hour <= 20 and probability >= 0.40:
        candidates.append(
            "This is a high-risk period because EV charging can coincide with HVAC, cooking and optional high-power loads such as the sauna."
        )
    elif 16 <= hour <= 22 and probability >= 0.20:
        candidates.append(
            "Evening demand can rise when EV charging, HVAC and household activities overlap."
        )

    # Frozen normal cooling targets are capped at 25 C and cooling starts
    # above target + 0.5 C. Outdoor temperature is only a weather-context
    # indicator; no future indoor state or realized HVAC mode is inspected.
    if temperature >= 25.5:
        candidates.append("Warm weather can increase cooling demand during this period.")

    # Union of frozen pool-circulation/heating operating support is 06:00-23:00.
    if 6 <= hour < 23:
        candidates.append("Pool circulation or heating can add to household demand during this period.")

    if bool(context["is_weekend"]) and 7 <= hour < 19:
        candidates.append("Weekend occupancy can increase daytime household activity.")

    if context["tariff_period"] == "PEAK_17_22":
        candidates.append("This also falls in the highest-price tariff period (€0.40/kWh).")

    if (hour >= 23 or hour < 7) and probability < 0.20:
        candidates.append(
            "Demand is usually lower overnight, although base loads, HVAC, pool systems and EV charging may remain active."
        )

    if not candidates:
        candidates.append("Expected demand and uncertainty follow the frozen household and weather patterns for this hour.")
    primary = candidates[0]
    secondary = candidates[1] if len(candidates) > 1 else ""
    return primary, secondary

