"""Deterministic lexicographic MILP for Stage 9."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import Any

from contract.production_schema import HVACProductionConstraint, OptimizationRequirements, ProductionEventConstraint
from contract.schema import LoadComponent as L
from hackowatt_stage7 import build_optimization_requirements

from .candidates import StartCandidate, coherent_candidates, interval_capacity
from .config import (
    BEHAVIORAL_COLUMNS,
    COMFORT_TOLERANCE_C,
    COST_TOLERANCE_EUR,
    EXPORT_PRICE_EUR_PER_KWH,
    FIXED_COLUMNS,
    REFERENCE_CAPACITY_KWP,
    ROOT,
    VALUE_TOLERANCE,
)
from .data import build_operational_context, load_retrospective_inputs, stage6_display_lookup, tariff_eur_per_kwh

VENDOR = Path(__file__).resolve().parent / "_vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))
import pulp  # type: ignore  # noqa: E402


@dataclass
class HVACVariables:
    temperature: list[Any]
    heat: list[Any]
    cool: list[Any]
    low_violation: dict[int, Any]
    high_violation: dict[int, Any]
    occupied: tuple[int, ...]

    @property
    def total_violation(self):
        return pulp.lpSum(self.low_violation.values()) + pulp.lpSum(self.high_violation.values())


@dataclass
class HVACComfortVariables:
    temperature: list[Any]
    action: list[Any]
    activity: list[Any]
    low_violation: dict[int, Any]
    high_violation: dict[int, Any]
    occupied: tuple[int, ...]

    @property
    def total_violation(self):
        return pulp.lpSum(self.low_violation.values()) + pulp.lpSum(self.high_violation.values())


def _add_hvac_comfort(
    model: Any,
    contract: HVACProductionConstraint,
    prefix: str,
) -> HVACComfortVariables:
    """Equivalent ternary heat/off/cool formulation for comfort proofs."""

    states = contract.hourly_states
    count = len(states)
    temperature = [pulp.LpVariable(f"{prefix}_temperature_{i}") for i in range(count + 1)]
    action = [pulp.LpVariable(f"{prefix}_action_{i}", lowBound=-1, upBound=1, cat="Integer") for i in range(count)]
    activity = [pulp.LpVariable(f"{prefix}_activity_{i}", lowBound=0, upBound=1) for i in range(count)]
    low_violation: dict[int, Any] = {}
    high_violation: dict[int, Any] = {}
    occupied = []
    model += temperature[0] == contract.initial_indoor_temperature_c
    big_m = 20.0
    for index, state in enumerate(states):
        model += activity[index] >= action[index]
        model += activity[index] >= -action[index]
        model += temperature[index + 1] == (
            temperature[index]
            + (state.outdoor_temperature_c - temperature[index]) / contract.thermal_time_constant_hours
            + action[index]
        )
        # action=-1 is cooling; action=+1 is heating. EMPTY/AWAY targets
        # bound active preconditioning but are not hard indoor-temperature
        # constraints: natural drift may cross them while HVAC is off.
        precondition_lower = min(contract.heating.lower_c, state.effective_heating_target_c)
        precondition_upper = max(contract.cooling.upper_c, state.effective_cooling_target_c)
        model += temperature[index + 1] >= precondition_lower - big_m * (action[index] + 1)
        model += temperature[index + 1] <= precondition_upper + big_m * (1 - action[index])
        if not state.away and state.occupancy_state in {"FULL", "PARTIAL"}:
            occupied.append(index)
            low_violation[index] = pulp.LpVariable(f"{prefix}_low_violation_{index}", lowBound=0)
            high_violation[index] = pulp.LpVariable(f"{prefix}_high_violation_{index}", lowBound=0)
            model += temperature[index] + low_violation[index] >= contract.heating.lower_c
            model += temperature[index] - high_violation[index] <= contract.cooling.upper_c
    return HVACComfortVariables(
        temperature, action, activity, low_violation, high_violation, tuple(occupied)
    )


def _physical_comfort_caps(
    contract: HVACProductionConstraint,
) -> tuple[dict[int, float], list[dict[str, Any]]]:
    """Continuous-control reachability lower bounds, later attained by binary HVAC.

    The relaxation permits fractional within-hour effect between off and the
    frozen +/-1 C effect, so its violation is a rigorous lower bound for the
    frozen binary controller.  The full MILP must attain every returned cap;
    otherwise Stage 9 stops.
    """

    lower_reachable = upper_reachable = contract.initial_indoor_temperature_c
    caps: dict[int, float] = {}
    proofs: list[dict[str, Any]] = []
    for index, state in enumerate(contract.hourly_states):
        occupied = not state.away and state.occupancy_state in {"FULL", "PARTIAL"}
        violation = 0.0
        direction = "none"
        if occupied and lower_reachable > contract.cooling.upper_c:
            if occupied:
                violation = lower_reachable - contract.cooling.upper_c
                direction = "above_cooling_upper"
            upper_reachable = lower_reachable
        elif occupied and upper_reachable < contract.heating.lower_c:
            if occupied:
                violation = contract.heating.lower_c - upper_reachable
                direction = "below_heating_lower"
            lower_reachable = upper_reachable
        elif occupied:
            lower_reachable = max(lower_reachable, contract.heating.lower_c)
            upper_reachable = min(upper_reachable, contract.cooling.upper_c)
        if occupied:
            caps[index] = max(violation, 0.0)
            if violation > COMFORT_TOLERANCE_C:
                proofs.append({
                    "timestamp": state.timestamp,
                    "minimum_unavoidable_violation_c": violation,
                    "direction": direction,
                    "relaxed_reachable_temperature_c": (
                        lower_reachable if direction == "above_cooling_upper" else upper_reachable
                    ),
                    "proof": "continuous-control reachability lower bound jointly attained by rated-power within-hour duty-cycle model",
                })
        natural_low = lower_reachable + (state.outdoor_temperature_c - lower_reachable) / contract.thermal_time_constant_hours
        natural_high = upper_reachable + (state.outdoor_temperature_c - upper_reachable) / contract.thermal_time_constant_hours
        precondition_lower = min(contract.heating.lower_c, state.effective_heating_target_c)
        precondition_upper = max(contract.cooling.upper_c, state.effective_cooling_target_c)
        cooled = natural_low + contract.cooling_effect_c_per_hour
        lower_reachable = (
            natural_low if natural_low < precondition_lower else max(cooled, precondition_lower)
        )
        heated = natural_high + contract.heating_effect_c_per_hour
        upper_reachable = (
            natural_high if natural_high > precondition_upper else min(heated, precondition_upper)
        )
    return caps, proofs


def _solver(kind: str = "highs") -> Any:
    if kind == "cbc":
        solver = pulp.PULP_CBC_CMD(
            msg=False,
            threads=1,
            gapRel=0.0,
            gapAbs=0.0,
            # CBC assigns a clock-based seed to zero. Both explicit non-zero
            # seeds are required for reproducible branch/cut decisions.
            options=["randomSeed 1", "randomCbcSeed 1"],
        )
        if not solver.available():
            raise RuntimeError("STOP: bundled CBC solver is unavailable")
        return solver
    solver = pulp.HiGHS(
        msg=False,
        threads=1,
        gapRel=0.0,
        gapAbs=0.0,
        random_seed=0,
    )
    if not solver.available():
        raise RuntimeError("STOP: bundled HiGHS solver is unavailable")
    return solver


def _solve(model: Any, label: str, solver_kind: str = "highs") -> None:
    status = model.solve(_solver(solver_kind))
    status_name = pulp.LpStatus[status]
    if status_name != "Optimal":
        raise RuntimeError(f"STOP: {label} solver status is {status_name}")


def _add_hvac(
    model: Any,
    contract: HVACProductionConstraint,
    prefix: str,
    binary_activation: bool = False,
) -> HVACVariables:
    states = contract.hourly_states
    count = len(states)
    temperature = [pulp.LpVariable(f"{prefix}_temperature_{i}") for i in range(count + 1)]
    # Fraction of the clock hour operated at the unchanged rated power and
    # unchanged full-duty thermal effect. This represents deterministic
    # within-hour ON/OFF duty cycling; heat/cool remain mutually exclusive.
    heat = [pulp.LpVariable(f"{prefix}_heat_{i}", lowBound=0, upBound=1) for i in range(count)]
    cool = [pulp.LpVariable(f"{prefix}_cool_{i}", lowBound=0, upBound=1) for i in range(count)]
    low_violation: dict[int, Any] = {}
    high_violation: dict[int, Any] = {}
    occupied = []
    model += temperature[0] == contract.initial_indoor_temperature_c
    heat_on = [pulp.LpVariable(f"{prefix}_heat_on_{i}", cat="Binary") for i in range(count)] if binary_activation else []
    cool_on = [pulp.LpVariable(f"{prefix}_cool_on_{i}", cat="Binary") for i in range(count)] if binary_activation else []
    for index, state in enumerate(states):
        model += heat[index] + cool[index] <= 1
        if binary_activation:
            model += heat[index] <= heat_on[index]
            model += cool[index] <= cool_on[index]
            model += heat_on[index] + cool_on[index] <= 1
        model += temperature[index + 1] == (
            temperature[index]
            + (state.outdoor_temperature_c - temperature[index]) / contract.thermal_time_constant_hours
            + contract.heating_effect_c_per_hour * heat[index]
            + contract.cooling_effect_c_per_hour * cool[index]
        )
        # Limited pre-conditioning uses the frozen mode-specific bounds. These
        # implications restrict active conditioning, without pretending that
        # an EMPTY/AWAY thermostat target is a hard physical temperature bound.
        # 20 C is a valid tight deactivation bound for the frozen Barcelona
        # temperature/effect range and materially strengthens the MILP.
        big_m = 20.0
        precondition_lower = min(contract.heating.lower_c, state.effective_heating_target_c)
        precondition_upper = max(contract.cooling.upper_c, state.effective_cooling_target_c)
        cooling_switch = cool_on[index] if binary_activation else cool[index]
        heating_switch = heat_on[index] if binary_activation else heat[index]
        model += temperature[index + 1] >= precondition_lower - big_m * (1 - cooling_switch)
        model += temperature[index + 1] <= precondition_upper + big_m * (1 - heating_switch)
        is_occupied = not state.away and state.occupancy_state in {"FULL", "PARTIAL"}
        if is_occupied:
            occupied.append(index)
            low_violation[index] = pulp.LpVariable(f"{prefix}_low_violation_{index}", lowBound=0)
            high_violation[index] = pulp.LpVariable(f"{prefix}_high_violation_{index}", lowBound=0)
            model += temperature[index] + low_violation[index] >= contract.heating.lower_c
            model += temperature[index] - high_violation[index] <= contract.cooling.upper_c
    return HVACVariables(temperature, heat, cool, low_violation, high_violation, tuple(occupied))


def _minimum_comfort(contract: HVACProductionConstraint) -> tuple[float, dict[int, float], list[dict[str, Any]]]:
    """Prove each chronological reachability bound and joint attainment."""

    caps, proofs = _physical_comfort_caps(contract)
    minimum_total = sum(caps.values())
    joint = pulp.LpProblem("stage9_joint_comfort_attainment", pulp.LpMinimize)
    joint_vars = _add_hvac(joint, contract, "joint", binary_activation=True)
    for index in joint_vars.occupied:
        joint += joint_vars.low_violation[index] + joint_vars.high_violation[index] <= caps[index] + COMFORT_TOLERANCE_C
    joint += joint_vars.total_violation
    _solve(joint, "joint physical comfort-bound attainment", "cbc")
    attained = float(pulp.value(joint_vars.total_violation))
    if attained > minimum_total + COMFORT_TOLERANCE_C * len(joint_vars.occupied):
        raise RuntimeError("STOP: physical comfort lower bounds are not jointly attainable")
    for item in proofs:
        item["proof"] = (
            "independent chronological reachable-temperature bound; all per-hour bounds "
            "jointly attained by the binary target-limited duty-cycle model"
        )
    return minimum_total, caps, proofs


def _base_load(row: dict[str, str]) -> float:
    return sum(float(row[column]) for column in FIXED_COLUMNS + BEHAVIORAL_COLUMNS)


def _add_coherent_events(
    model: Any,
    events: list[ProductionEventConstraint],
    timeline: list[datetime],
    hourly_event_load: list[Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[Any]]]:
    decisions: dict[str, dict[str, Any]] = {}
    selection_vars: dict[str, list[Any]] = {}
    coherent_components = {L.DISHWASHER, L.WASHER, L.DRYER, L.SAUNA, L.POOL_HEATING}
    for event in events:
        if event.component not in coherent_components:
            continue
        candidates = coherent_candidates(event, timeline)
        variables = [pulp.LpVariable(f"event_{event.event_id}_{i}", cat="Binary") for i in range(len(candidates))]
        model += pulp.lpSum(variables) == 1
        selection_vars[event.event_id] = variables
        for candidate, variable in zip(candidates, variables):
            for hour_index, energy in candidate.allocations:
                hourly_event_load[hour_index] += energy * variable
        decisions[event.event_id] = {"event": event, "candidates": candidates, "variables": variables}

    for event_id, decision in decisions.items():
        event = decision["event"]
        if not event.depends_on_event_id:
            continue
        if event.depends_on_event_id not in decisions:
            raise RuntimeError(f"STOP: missing dependency {event.depends_on_event_id} for {event_id}")
        dependency = decisions[event.depends_on_event_id]
        horizon_start = timeline[0]
        dependency_end = pulp.lpSum(
            ((candidate.end - horizon_start).total_seconds() / 3600.0) * variable
            for candidate, variable in zip(dependency["candidates"], dependency["variables"])
        )
        event_start = pulp.lpSum(
            ((candidate.start - horizon_start).total_seconds() / 3600.0) * variable
            for candidate, variable in zip(decision["candidates"], decision["variables"])
        )
        model += event_start >= dependency_end
    return decisions, selection_vars


def _add_interval_events(
    model: Any,
    events: list[ProductionEventConstraint],
    timeline: list[datetime],
    hourly_event_load: list[Any],
) -> dict[str, dict[str, Any]]:
    horizon_start, horizon_end = timeline[0], timeline[-1] + timedelta(hours=1)
    decisions: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.component not in {L.EV1, L.EV2, L.POOL_CIRCULATION}:
            continue
        interval = event.availability_intervals[0]
        start = datetime.fromisoformat(interval.start)
        end = datetime.fromisoformat(interval.end) if interval.end else horizon_end
        if start >= horizon_end or end <= horizon_start:
            decisions[event.event_id] = {"event": event, "variables": {}, "status": "boundary_outside_window"}
            continue
        capacity = interval_capacity(max(start, horizon_start), min(end, horizon_end), event.power_kw, timeline)
        if sum(capacity.values()) + VALUE_TOLERANCE < event.energy_kwh:
            raise RuntimeError(
                f"STOP: {event.event_id} needs {event.energy_kwh} kWh but only {sum(capacity.values())} kWh is feasible"
            )
        variables = {
            index: pulp.LpVariable(f"event_{event.event_id}_{index}", lowBound=0, upBound=limit)
            for index, limit in capacity.items()
        }
        model += pulp.lpSum(variables.values()) == event.energy_kwh
        for index, variable in variables.items():
            hourly_event_load[index] += variable
        decisions[event.event_id] = {"event": event, "variables": variables, "status": "satisfied"}
    return decisions


def _build_full_model(
    inputs: OptimizationRequirements,
    actual_rows: list[dict[str, str]],
    pv_rows: list[dict[str, Any]],
    comfort_minimum: float,
    comfort_caps: dict[int, float],
) -> tuple[Any, dict[str, Any]]:
    model = pulp.LpProblem("stage9_cost_and_peak", pulp.LpMinimize)
    # Mode binaries make controller targets authoritative whenever equipment is
    # active, while leaving natural drift unconstrained when both modes are off.
    hvac = _add_hvac(model, inputs.hvac, "full", binary_activation=True)
    model += hvac.total_violation <= comfort_minimum + COMFORT_TOLERANCE_C
    for index in hvac.occupied:
        model += hvac.low_violation[index] + hvac.high_violation[index] <= comfort_caps[index] + COMFORT_TOLERANCE_C

    timeline = [datetime.fromisoformat(row["timestamp"]) for row in actual_rows]
    hourly_event_load: list[Any] = [0.0 for _ in timeline]
    coherent, _ = _add_coherent_events(model, list(inputs.events), timeline, hourly_event_load)
    interval = _add_interval_events(model, list(inputs.events), timeline, hourly_event_load)

    load = []
    grid_import = []
    exported = []
    cost_terms = []
    peak = pulp.LpVariable("optimized_peak_kwh", lowBound=0)
    for index, (row, pv) in enumerate(zip(actual_rows, pv_rows)):
        hvac_load = inputs.hvac.heating.rated_power_kw * hvac.heat[index] + inputs.hvac.cooling.rated_power_kw * hvac.cool[index]
        expression = _base_load(row) + hourly_event_load[index] + hvac_load
        load.append(expression)
        grid = pulp.LpVariable(f"grid_import_{index}", lowBound=0)
        export = pulp.LpVariable(f"exported_pv_{index}", lowBound=0)
        model += grid - export == expression - float(pv["pv_generation_kwh"])
        model += peak >= expression
        grid_import.append(grid)
        exported.append(export)
        cost_terms.append(tariff_eur_per_kwh(row["timestamp"]) * grid - EXPORT_PRICE_EUR_PER_KWH * export)
    cost = pulp.lpSum(cost_terms)
    return model, {
        "hvac": hvac,
        "coherent": coherent,
        "interval": interval,
        "load": load,
        "grid_import": grid_import,
        "exported": exported,
        "cost": cost,
        "peak": peak,
        "timeline": timeline,
    }


def _selected_candidate(decision: dict[str, Any]) -> StartCandidate:
    chosen = [
        candidate for candidate, variable in zip(decision["candidates"], decision["variables"])
        if variable.value() > 0.5
    ]
    if len(chosen) != 1:
        raise RuntimeError("STOP: coherent event has no unique selected start")
    return chosen[0]


def optimize_retrospective(capacity_kwp: float = REFERENCE_CAPACITY_KWP) -> dict[str, Any]:
    """Optimize the frozen Aug-Sep realization with exact Stage 3 services."""

    inputs = build_optimization_requirements()
    actual_rows, pv_rows = load_retrospective_inputs(capacity_kwp)
    comfort_minimum, comfort_caps, proofs = _minimum_comfort(inputs.hvac)
    model, variables = _build_full_model(inputs, actual_rows, pv_rows, comfort_minimum, comfort_caps)

    model.setObjective(variables["cost"])
    _solve(model, "net cost", "cbc")
    minimum_cost = float(pulp.value(variables["cost"]))
    model += variables["cost"] <= minimum_cost + COST_TOLERANCE_EUR
    model.setObjective(variables["peak"])
    _solve(model, "peak tie-break", "cbc")
    minimum_peak = float(variables["peak"].value())

    optimized_load = [float(pulp.value(value)) for value in variables["load"]]
    temperatures = [float(value.value()) for value in variables["hvac"].temperature[:-1]]
    heat_values = [float(value.value()) for value in variables["hvac"].heat]
    cool_values = [float(value.value()) for value in variables["hvac"].cool]
    # Report the physical band exceedance, not a solver slack variable that is
    # no longer in the tertiary objective and can therefore be non-minimal
    # inside its already-proven cap.
    violations = {
        index: max(
            inputs.hvac.heating.lower_c - temperatures[index],
            temperatures[index] - inputs.hvac.cooling.upper_c,
            0.0,
        )
        for index in variables["hvac"].occupied
    }

    event_rows = []
    optimized_allocations: dict[str, dict[int, float]] = {}
    for event in inputs.events:
        if event.event_id in variables["coherent"]:
            chosen = _selected_candidate(variables["coherent"][event.event_id])
            optimized_start, optimized_end = chosen.start, chosen.end
            allocation = dict(chosen.allocations)
            status = "satisfied"
        else:
            decision = variables["interval"][event.event_id]
            allocation = {index: float(value.value()) for index, value in decision["variables"].items() if value.value() > VALUE_TOLERANCE}
            status = decision["status"]
            if allocation:
                indices = sorted(allocation)
                availability = event.availability_intervals[0]
                availability_start = datetime.fromisoformat(availability.start)
                optimized_start = max(variables["timeline"][indices[0]], availability_start)
                last_start = max(variables["timeline"][indices[-1]], availability_start)
                optimized_end = last_start + timedelta(hours=allocation[indices[-1]] / event.power_kw)
            else:
                optimized_start = datetime.fromisoformat(event.actual_start)
                optimized_end = datetime.fromisoformat(event.actual_end)
        optimized_allocations[event.event_id] = allocation
        original_start = datetime.fromisoformat(event.actual_start)
        shift_hours = (optimized_start - original_start).total_seconds() / 3600.0
        event_rows.append({
            "event_id": event.event_id,
            "component": event.component.value,
            "original_start": event.actual_start,
            "optimized_start": optimized_start.isoformat(),
            "original_end": event.actual_end,
            "optimized_end": optimized_end.isoformat(),
            "energy_kwh": event.energy_kwh,
            "original_energy_kwh": event.energy_kwh,
            "optimized_energy_kwh": sum(allocation.values()) if allocation else event.delivered_in_window_kwh or 0.0,
            "duration_hours": event.duration_hours,
            "power_kw": event.power_kw,
            "shift_hours": shift_hours,
            "constraint_status": status,
            "depends_on_event_id": event.depends_on_event_id or "",
            "vehicle_id": event.vehicle_id or "",
            "deadline": event.deadline or "",
            "availability_start": event.availability_intervals[0].start if event.availability_intervals else "",
            "availability_end": (event.availability_intervals[-1].end or "") if event.availability_intervals else "",
            "latest_start": event.latest_start or "",
            "coherent_cycle": event.coherent_cycle,
            "same_calendar_day": event.same_calendar_day,
        })

    current_hvac_energy = sum(float(row["hvac_kwh"]) for row in actual_rows)
    optimized_hvac_energy = sum(
        inputs.hvac.heating.rated_power_kw * heat + inputs.hvac.cooling.rated_power_kw * cool
        for heat, cool in zip(heat_values, cool_values)
    )
    event_rows.append({
        "event_id": inputs.hvac.event_id,
        "component": "hvac",
        "original_start": actual_rows[0]["timestamp"],
        "optimized_start": actual_rows[0]["timestamp"],
        "original_end": (variables["timeline"][-1] + timedelta(hours=1)).isoformat(),
        "optimized_end": (variables["timeline"][-1] + timedelta(hours=1)).isoformat(),
        "energy_kwh": current_hvac_energy,
        "original_energy_kwh": current_hvac_energy,
        "optimized_energy_kwh": optimized_hvac_energy,
        "duration_hours": len(actual_rows),
        "power_kw": max(inputs.hvac.heating.rated_power_kw, inputs.hvac.cooling.rated_power_kw),
        "shift_hours": 0.0,
        "constraint_status": "comfort_violation_lexicographically_minimized",
        "depends_on_event_id": "",
        "vehicle_id": "",
        "deadline": "",
        "availability_start": actual_rows[0]["timestamp"],
        "availability_end": (variables["timeline"][-1] + timedelta(hours=1)).isoformat(),
        "latest_start": "",
        "coherent_cycle": False,
        "same_calendar_day": False,
    })
    return {
        "mode": "retrospective_validation",
        "capacity_kwp": float(capacity_kwp),
        "inputs": inputs,
        "actual_rows": actual_rows,
        "pv_rows": pv_rows,
        "stage6_lookup": stage6_display_lookup(),
        "optimized_load": optimized_load,
        "optimized_temperature": temperatures,
        "optimized_terminal_temperature_c": float(variables["hvac"].temperature[-1].value()),
        "optimized_heat": heat_values,
        "optimized_cool": cool_values,
        "optimized_violations": violations,
        "comfort_minimum_degree_hours": comfort_minimum,
        "comfort_caps": comfort_caps,
        "comfort_proofs": proofs,
        "event_rows": event_rows,
        "optimized_allocations": optimized_allocations,
        "minimum_net_cost_before_peak_tiebreak_eur": minimum_cost,
        "final_net_cost_eur": float(pulp.value(variables["cost"])),
        "optimized_peak_kwh": max(optimized_load),
        "solver": "PuLP 3.3.0 with bundled CBC for joint comfort attainment and event/cost/peak MILP, one thread, fixed seed, zero MIP gap",
    }


__all__ = ["optimize_retrospective", "build_operational_context"]
