"""Event sources: BigQuery/DebugView CSV export, the GA4 Data API, or a demo set."""

from __future__ import annotations

import csv
import random
from pathlib import Path

from .models import ObservedEvent, PlanEvent

_EVENT_COL = ("event_name", "eventname", "event")
_PARAM_KEY_COL = ("event_params_key", "event_params.key", "param_key", "key")
_OCCURRENCE_COLS = ("event_timestamp", "user_pseudo_id", "ga_session_id", "event_bundle_sequence_id")
_IGNORED_WIDE = {"event_date", "event_timestamp", "user_pseudo_id", "ga_session_id", "event_bundle_sequence_id", "count", "event_count"}


def _pick(header: list[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {h.strip().lower(): h for h in header}
    for c in candidates:
        if c in lowered:
            return lowered[c]
    return None


def load_export_csv(path: str | Path) -> list[ObservedEvent]:
    """Parse a GA4 event export.

    Two shapes are recognised automatically:

    * **Long** (BigQuery ``UNNEST(event_params)`` flat export): one row per
      (event, parameter) with an ``event_params_key`` column. Occurrences are
      identified by ``event_timestamp`` + ``user_pseudo_id`` when present.
    * **Wide** (DebugView / GTM preview export, or a hand-made sheet): one row
      per event with parameters as columns; a non-empty cell means "present".
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        event_col = _pick(header, _EVENT_COL)
        if not event_col:
            raise ValueError(f"No event-name column found in {path} (looked for {', '.join(_EVENT_COL)})")
        key_col = _pick(header, _PARAM_KEY_COL)
        rows = list(reader)

    events: dict[str, ObservedEvent] = {}

    if key_col:
        id_cols = [c for c in header if c.strip().lower() in _OCCURRENCE_COLS]
        value_cols = [c for c in header if "value" in c.lower() and c != key_col]
        occurrences: dict[str, set] = {}
        param_hits: dict[str, dict[str, set]] = {}
        for i, row in enumerate(rows):
            name = (row.get(event_col) or "").strip()
            if not name:
                continue
            occ_id = tuple(row.get(c, "") for c in id_cols) if id_cols else (i,)
            occurrences.setdefault(name, set()).add(occ_id)
            key = (row.get(key_col) or "").strip()
            has_value = any((row.get(c) or "").strip() not in ("", "(not set)", "null") for c in value_cols) if value_cols else True
            if key and has_value:
                param_hits.setdefault(name, {}).setdefault(key, set()).add(occ_id)
        for name, occ in occurrences.items():
            events[name] = ObservedEvent(
                name=name,
                count=len(occ),
                param_counts={k: len(v) for k, v in param_hits.get(name, {}).items()},
            )
    else:
        count_col = _pick(header, ("event_count", "count"))
        param_cols = [c for c in header if c != event_col and c != count_col and c.strip().lower() not in _IGNORED_WIDE]
        for row in rows:
            name = (row.get(event_col) or "").strip()
            if not name:
                continue
            n = 1
            if count_col:
                try:
                    n = int(float(row.get(count_col) or 1))
                except ValueError:
                    n = 1
            ev = events.setdefault(name, ObservedEvent(name=name))
            ev.count += n
            for c in param_cols:
                if (row.get(c) or "").strip() not in ("", "(not set)", "null"):
                    ev.param_counts[c.strip()] = ev.param_counts.get(c.strip(), 0) + n
    return list(events.values())


# ─── GA4 Data API ─────────────────────────────────────────────────────────────


def fetch_api(property_id: str, credentials_path: str, days: int, plan: list[PlanEvent]) -> list[ObservedEvent]:
    """Pull event counts from the GA4 Data API and, where possible, parameter coverage.

    GA4 only exposes an event parameter through the API once it is registered
    as a *custom dimension* (event scope). For each required parameter we try
    the ``customEvent:<param>`` dimension; if the API rejects it the parameter
    is reported as *unverifiable* rather than silently marked present or
    missing — that was a real defect in v1.
    """
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import DateRange, Dimension, Filter, FilterExpression, Metric, RunReportRequest
        from google.oauth2 import service_account
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise SystemExit("API mode needs the optional extra: pip install 'ga4audit[api]'") from exc

    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=["https://www.googleapis.com/auth/analytics.readonly"]
    )
    client = BetaAnalyticsDataClient(credentials=creds)
    date_range = DateRange(start_date=f"{days}daysAgo", end_date="today")
    prop = f"properties/{property_id}"

    resp = client.run_report(
        RunReportRequest(property=prop, dimensions=[Dimension(name="eventName")], metrics=[Metric(name="eventCount")],
                         date_ranges=[date_range], limit=10000)
    )
    events = {
        r.dimension_values[0].value: ObservedEvent(name=r.dimension_values[0].value, count=int(r.metric_values[0].value))
        for r in resp.rows
    }

    for pe in plan:
        ev = events.get(pe.name)
        if not ev:
            continue
        for param in pe.required_parameters:
            try:
                r2 = client.run_report(
                    RunReportRequest(
                        property=prop,
                        dimensions=[Dimension(name=f"customEvent:{param}")],
                        metrics=[Metric(name="eventCount")],
                        date_ranges=[date_range],
                        dimension_filter=FilterExpression(
                            filter=Filter(field_name="eventName", string_filter=Filter.StringFilter(value=pe.name))
                        ),
                        limit=10000,
                    )
                )
                populated = sum(int(r.metric_values[0].value) for r in r2.rows if r.dimension_values[0].value not in ("(not set)", ""))
                ev.param_counts[param] = populated
            except Exception:  # unregistered dimension → InvalidArgument
                ev.unverifiable_params.add(param)
    return list(events.values())


# ─── Demo ─────────────────────────────────────────────────────────────────────


def demo_events(plan: list[PlanEvent], seed: int = 7) -> list[ObservedEvent]:
    """Deterministic synthetic data that exercises every finding type."""
    rng = random.Random(seed)
    out: list[ObservedEvent] = []
    for i, pe in enumerate(plan):
        if i % 4 == 3:
            continue  # every 4th event "never fires"
        count = rng.randint(200, 4000)
        ev = ObservedEvent(name=pe.name, count=count)
        for j, p in enumerate(pe.required_parameters):
            ev.param_counts[p] = count if (i + j) % 3 else int(count * 0.4)  # some partial coverage
        out.append(ev)
    if plan:
        first = plan[0].name
        out.append(ObservedEvent(name=first.title(), count=44))  # e.g. Purchase → naming issue
        if "_" in first:
            out.append(ObservedEvent(name=first.replace("_", "-"), count=12))
    out += [ObservedEvent("page_view", 51230), ObservedEvent("gtm.click", 913), ObservedEvent("checkout_start", 211)]
    return out
