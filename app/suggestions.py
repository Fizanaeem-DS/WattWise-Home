"""Readable descriptions of shifts already present in frozen Stage 9."""

from __future__ import annotations

from hackowatt_stage11.models import ShiftedEvent
from theme import COMPONENT_LABELS


def schedule_change_sentence(event: ShiftedEvent) -> str:
    component = COMPONENT_LABELS[event.component]
    before = event.original_start[11:16]
    after = event.optimized_start[11:16]
    status = "all scheduling requirements met" if event.constraint_status == "satisfied" else event.constraint_status
    return (
        f"{component}: {before} → {after}; {event.energy_kwh:.2f} kWh and "
        f"{event.duration_hours:.2f} h preserved ({status})."
    )
