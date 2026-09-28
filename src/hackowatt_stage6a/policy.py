"""Explicit Stage 6A-only optional-event/AWAY infeasibility policy."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

import hackowatt_stage3b.generator as stage3b_generator


OPTIONAL_SYSTEMS = {"pool heating": "pool_heating", "sauna": "sauna"}


def _at(day: date, hour: float) -> datetime:
    return datetime.combine(day, time(0), tzinfo=ZoneInfo(stage3b_generator.TIMEZONE)) + timedelta(hours=hour)


def feasible_start_segments(
    day: date,
    lower_hour: float,
    upper_hour: float,
    duration_hours: float,
    away_intervals: list[dict[str, Any]],
) -> list[tuple[datetime, datetime]]:
    """Recompute the frozen complete-event feasible start support exactly."""
    lower = _at(day, lower_hour)
    upper = _at(day, upper_hour)
    duration = timedelta(hours=duration_hours)
    segments = [(lower, upper)]
    for away in away_intervals:
        forbidden_lower = away["start"] - duration
        forbidden_upper = away["end"]
        updated: list[tuple[datetime, datetime]] = []
        for start, end in segments:
            if forbidden_upper <= start or forbidden_lower >= end:
                updated.append((start, end))
                continue
            if start <= forbidden_lower:
                updated.append((start, min(end, forbidden_lower)))
            if forbidden_upper <= end:
                updated.append((max(start, forbidden_upper), end))
        segments = [(start, end) for start, end in updated if start <= end]
    return segments


class OptionalEventAwayPolicy:
    """Narrow adapter around frozen placement/allocation functions."""

    def __init__(self) -> None:
        self.suppressions: list[dict[str, Any]] = []
        self._pending_by_interval: dict[tuple[str, str], dict[str, Any]] = {}
        self._original_random_start = stage3b_generator._random_start_outside_away
        self._original_allocate = stage3b_generator._allocate_constant_power

    def random_start(
        self,
        rng,
        day: date,
        lower_hour: float,
        upper_hour: float,
        duration_hours: float,
        away_intervals: list[dict[str, Any]],
        system: str,
    ) -> tuple[datetime, datetime, bool, int]:
        try:
            return self._original_random_start(
                rng,
                day,
                lower_hour,
                upper_hour,
                duration_hours,
                away_intervals,
                system,
            )
        except stage3b_generator.NoFeasibleStartError:
            if system not in OPTIONAL_SYSTEMS:
                raise
            segments = feasible_start_segments(
                day, lower_hour, upper_hour, duration_hours, away_intervals
            )
            if segments:
                raise AssertionError(
                    f"Suppression attempted for feasible {system} event on {day.isoformat()}"
                )
            lower = _at(day, lower_hour)
            end = lower + timedelta(hours=duration_hours)
            conflicts = [
                {
                    "event_id": away["event_id"],
                    "start": away["start"].isoformat(),
                    "end": away["end"].isoformat(),
                }
                for away in away_intervals
                if away["end"] > lower
                and away["start"] < _at(day, upper_hour) + timedelta(hours=duration_hours)
            ]
            record = {
                "event_type": OPTIONAL_SYSTEMS[system],
                "date": day.isoformat(),
                "suppressed_due_to_away_conflict": True,
                "suppression_reason": "no_feasible_start_outside_away",
                "sampled_duration_hours": duration_hours,
                "sampled_power_kw": None,
                "required_energy_kwh": None,
                "allocated_energy_kwh": 0.0,
                "permitted_start_range": f"{lower_hour:02.0f}:00-{upper_hour:02.0f}:00",
                "permitted_start_lower_hour": lower_hour,
                "permitted_start_upper_hour": upper_hour,
                "conflicting_away_intervals": conflicts,
                "feasible_start_support_exhaustively_empty": True,
                "activation_redrawn": False,
                "duration_redrawn_or_shortened": False,
                "power_redrawn": False,
                "start_range_extended": False,
                "moved_to_another_day": False,
                "away_event_altered": False,
                "seed_substituted": False,
            }
            self.suppressions.append(record)
            self._pending_by_interval[(lower.isoformat(), end.isoformat())] = record
            # The caller needs interval-shaped values to continue constructing
            # its temporary ledger. Allocation is intercepted and forced to
            # exactly zero; the temporary ledger is then explicitly annotated
            # with no placed start/end.
            return lower, lower, True, 0

    def allocate(
        self,
        start: datetime,
        end: datetime,
        power_kw: float,
        timestamps,
        index_by_timestamp,
        target,
        dataset_start: datetime,
        dataset_end: datetime,
    ):
        record = self._pending_by_interval.pop((start.isoformat(), end.isoformat()), None)
        if record is not None:
            record["sampled_power_kw"] = power_kw
            record["required_energy_kwh"] = power_kw * record["sampled_duration_hours"]
            return [], 0.0
        return self._original_allocate(
            start,
            end,
            power_kw,
            timestamps,
            index_by_timestamp,
            target,
            dataset_start,
            dataset_end,
        )

    @contextmanager
    def installed(self) -> Iterator["OptionalEventAwayPolicy"]:
        stage3b_generator._random_start_outside_away = self.random_start
        stage3b_generator._allocate_constant_power = self.allocate
        try:
            yield self
        finally:
            stage3b_generator._random_start_outside_away = self._original_random_start
            stage3b_generator._allocate_constant_power = self._original_allocate

    def annotate_ledger(self, ledger_path: Path) -> dict[str, Any]:
        if self._pending_by_interval:
            raise AssertionError("A suppressed optional event was not passed to allocation")
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        for record in self.suppressions:
            key = "pool_heating_events" if record["event_type"] == "pool_heating" else "sauna_events"
            matches = [
                event
                for event in ledger[key]
                if event["date"] == record["date"]
                and abs(event["duration_hours"] - record["sampled_duration_hours"]) < 1e-12
                and event["allocated_energy_kwh"] == 0.0
                and not event.get("suppressed_due_to_away_conflict", False)
            ]
            if len(matches) != 1:
                raise AssertionError(f"Could not uniquely identify suppressed {record['event_type']} ledger event")
            event = matches[0]
            event.update({
                "start": None,
                "end": None,
                "initial_sampled_start": None,
                "suppressed_due_to_away_conflict": True,
                "suppression_reason": "no_feasible_start_outside_away",
                "permitted_start_range": record["permitted_start_range"],
                "conflicting_away_intervals": record["conflicting_away_intervals"],
            })
            record["event_id"] = event["event_id"]
        ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return ledger

