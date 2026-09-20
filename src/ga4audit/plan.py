"""Load a tracking / measurement plan from JSON or CSV.

Accepts both historical formats (``name`` from ga4-event-auditor v1 and
``event_name`` from ga4-event-tracking-auditor) so existing plans keep working.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import PlanEvent


def _split(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    return tuple(p.strip() for p in str(value).replace(";", ",").replace("|", ",").split(",") if p.strip())


def _event_from_dict(d: dict) -> PlanEvent:
    name = (d.get("event_name") or d.get("name") or "").strip()
    if not name:
        raise ValueError(f"Plan entry without an event name: {d}")
    try:
        minimum = int(d.get("expected_minimum_count") or d.get("min_count") or 1)
    except (TypeError, ValueError):
        minimum = 1
    return PlanEvent(
        name=name,
        required_parameters=_split(d.get("required_parameters") or d.get("required_params")),
        optional_parameters=_split(d.get("optional_parameters") or d.get("optional_params")),
        expected_minimum_count=max(minimum, 0),
    )


def load_plan(path: str | Path) -> tuple[list[PlanEvent], dict]:
    """Return (events, metadata). Metadata carries e.g. ``property_id`` from JSON plans."""
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with open(p, newline="", encoding="utf-8-sig") as f:
            events = [_event_from_dict(row) for row in csv.DictReader(f) if any(row.values())]
        return events, {}
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    raw_events = data["events"] if isinstance(data, dict) else data
    meta = {k: v for k, v in data.items() if k != "events"} if isinstance(data, dict) else {}
    events = [_event_from_dict(e) for e in raw_events]
    seen: set[str] = set()
    for e in events:
        if e.name in seen:
            raise ValueError(f"Duplicate event in plan: {e.name}")
        seen.add(e.name)
    return events, meta
