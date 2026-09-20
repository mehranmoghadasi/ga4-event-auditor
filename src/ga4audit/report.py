"""Render an AuditReport to console, Markdown, JSON, and CSV."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from .models import AuditReport, Status

RED, YEL, GRN, CYN, DIM, BOLD, RST = "\033[91m", "\033[93m", "\033[92m", "\033[96m", "\033[2m", "\033[1m", "\033[0m"


def _param_summary(f) -> str:
    bits = []
    if f.missing_params:
        bits.append("missing: " + ", ".join(f.missing_params))
    if f.partial_params:
        bits.append("partial: " + ", ".join(f"{p} ({c:.0%})" for p, c in f.partial_params.items()))
    if f.unverifiable_params:
        bits.append("unverifiable via API: " + ", ".join(f.unverifiable_params))
    return "; ".join(bits)


def render_console(r: AuditReport, color: bool = True) -> str:
    c = (lambda code, s: f"{code}{s}{RST}") if color else (lambda code, s: s)
    n = len(r.findings)
    lines = [c(BOLD, f"GA4 Event Audit — {r.period or 'export'}"), f"Source: {r.source}   Plan events: {n}", "━" * 56]
    groups = [
        (Status.PASS, GRN, "✅ PASSING"),
        (Status.PARAM_ISSUES, YEL, "⚠️  PARAMETER ISSUES"),
        (Status.BELOW_EXPECTED, CYN, "📉 BELOW EXPECTED VOLUME"),
        (Status.MISSING, RED, "❌ NOT FIRING"),
    ]
    for status, col, label in groups:
        items = r.by_status(status)
        if not items:
            continue
        lines.append("")
        lines.append(c(col, f"{label} ({len(items)}/{n})"))
        for f in items:
            if status is Status.MISSING:
                lines.append(f"  {f.plan.name:<24} 0 occurrences")
            elif status is Status.BELOW_EXPECTED:
                lines.append(f"  {f.plan.name:<24} {f.count:>7,}  (expected ≥ {f.plan.expected_minimum_count:,})")
            else:
                lines.append(f"  {f.plan.name:<24} {f.count:>7,}  {_param_summary(f)}".rstrip())
    if r.naming_issues:
        lines += ["", c(YEL, f"🏷️  NAMING ISSUES ({len(r.naming_issues)})")]
        lines += [f"  {i.observed:<24} {i.count:>7,}  → should be {i.should_be}" for i in r.naming_issues]
    if r.ghost_events:
        lines += ["", c(DIM, f"👻 GHOST EVENTS — firing but not in plan ({len(r.ghost_events)})")]
        lines += [f"  {g.name:<24} {g.count:>7,}" for g in r.ghost_events]
    col = GRN if r.health_score >= 80 else YEL if r.health_score >= 60 else RED
    lines += ["", "━" * 56, c(col, f"Health score: {r.health_score}/100")]
    return "\n".join(lines)


def render_markdown(r: AuditReport) -> str:
    head = f"**Source:** {r.source} · **Plan events:** {len(r.findings)} · **Health score:** {r.health_score}/100"
    out = [f"# GA4 Event Audit — {r.period or 'export'}", "", head, ""]
    out += ["| Event | Status | Occurrences | Details |", "|---|---|---:|---|"]
    for f in r.findings:
        detail = _param_summary(f) if f.status is Status.PARAM_ISSUES else (
            f"expected ≥ {f.plan.expected_minimum_count:,}" if f.status is Status.BELOW_EXPECTED else "")
        out.append(f"| `{f.plan.name}` | {f.status.value} | {f.count:,} | {detail} |")
    if r.naming_issues:
        out += ["", "## Naming issues", ""] + [f"- `{i.observed}` ({i.count:,}) → rename to `{i.should_be}`" for i in r.naming_issues]
    if r.ghost_events:
        out += ["", "## Ghost events (not in plan)", ""] + [f"- `{g.name}` ({g.count:,})" for g in r.ghost_events]
    return "\n".join(out) + "\n"


def write_all(r: AuditReport, out_dir: str | Path) -> dict[str, Path]:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    paths = {"markdown": d / "audit_report.md", "json": d / "audit_report.json", "csv": d / "audit_report.csv"}
    paths["markdown"].write_text(render_markdown(r), encoding="utf-8")
    payload = {
        "health_score": r.health_score,
        "source": r.source,
        "period": r.period,
        "events": [
            {**asdict(f), "status": f.status.value, "plan": asdict(f.plan)} for f in r.findings
        ],
        "naming_issues": [asdict(i) for i in r.naming_issues],
        "ghost_events": [asdict(g) for g in r.ghost_events],
    }
    paths["json"].write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with open(paths["csv"], "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["event", "status", "occurrences", "missing_params", "partial_params", "unverifiable_params", "unexpected_params"])
        for x in r.findings:
            w.writerow([x.plan.name, x.status.value, x.count, "|".join(x.missing_params),
                        "|".join(f"{p}:{c:.2f}" for p, c in x.partial_params.items()),
                        "|".join(x.unverifiable_params), "|".join(x.unexpected_params)])
        for i in r.naming_issues:
            w.writerow([i.observed, "naming_issue", i.count, "", "", "", f"should_be={i.should_be}"])
        for g in r.ghost_events:
            w.writerow([g.name, "ghost", g.count, "", "", "", ""])
    return paths
