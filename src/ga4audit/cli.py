"""Command-line entry point: ``ga4audit``."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .engine import audit
from .plan import load_plan
from .report import render_console, write_all
from .sources import demo_events, fetch_api, load_export_csv


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ga4audit", description="Audit a GA4 implementation against a tracking plan")
    p.add_argument("--version", action="version", version=f"ga4audit {__version__}")
    p.add_argument("--plan", required=True, help="Tracking plan (JSON or CSV)")
    p.add_argument("--source", choices=["export", "api", "demo"], default="export")
    p.add_argument("--events", help="[export] GA4 event export CSV (BigQuery long or wide format)")
    p.add_argument("--credentials", help="[api] service-account JSON key")
    p.add_argument("--property", help="[api] GA4 property ID (falls back to plan's property_id)")
    p.add_argument("--days", type=int, default=30, help="[api] look-back window")
    p.add_argument("--coverage-threshold", type=float, default=0.95, help="Param present in < this share of events = partial")
    p.add_argument("--output", help="Directory for audit_report.{md,json,csv}")
    p.add_argument("--fail-under", type=int, help="Exit 1 if health score is below this (CI gate)")
    p.add_argument("--no-color", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        plan, meta = load_plan(a.plan)
        if a.source == "export":
            if not a.events:
                raise SystemExit("--events is required with --source export")
            observed, period = load_export_csv(a.events), a.events
        elif a.source == "api":
            prop = a.property or meta.get("property_id")
            if not (a.credentials and prop):
                raise SystemExit("--credentials and --property (or property_id in the plan) are required for --source api")
            observed, period = fetch_api(str(prop), a.credentials, a.days, plan), f"property {prop}, last {a.days} days"
        else:
            observed, period = demo_events(plan), "demo data"
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    report = audit(plan, observed, coverage_threshold=a.coverage_threshold, source=a.source, period=period)
    print(render_console(report, color=not a.no_color))
    if a.output:
        paths = write_all(report, a.output)
        print("\nSaved: " + ", ".join(str(p) for p in paths.values()))
    if a.fail_under is not None and report.health_score < a.fail_under:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
