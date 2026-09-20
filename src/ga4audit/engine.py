"""Compare observed GA4 events with the plan and score the implementation."""

from __future__ import annotations

import re

from .models import GA4_AUTO_EVENTS, AuditReport, EventFinding, GhostEvent, NamingIssue, ObservedEvent, PlanEvent, Status

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def canonical(name: str) -> str:
    """Normalise ``Add_To_Cart`` / ``add-to-cart`` / ``addToCart`` to ``add_to_cart``."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name.strip())
    return _NON_ALNUM.sub("_", s.lower()).strip("_")


def audit(
    plan: list[PlanEvent],
    observed: list[ObservedEvent],
    *,
    coverage_threshold: float = 0.95,
    source: str = "export",
    period: str = "",
) -> AuditReport:
    by_name = {e.name: e for e in observed}
    plan_names = {p.name for p in plan}
    canon_plan = {canonical(p.name): p.name for p in plan}

    findings: list[EventFinding] = []
    for pe in plan:
        ev = by_name.get(pe.name)
        if ev is None or ev.count == 0:
            findings.append(EventFinding(plan=pe, status=Status.MISSING))
            continue
        f = EventFinding(plan=pe, status=Status.PASS, count=ev.count)
        for param in pe.required_parameters:
            if param in ev.unverifiable_params:
                f.unverifiable_params.append(param)
                continue
            cov = ev.param_coverage(param)
            if cov == 0.0:
                f.missing_params.append(param)
            elif cov < coverage_threshold:
                f.partial_params[param] = cov
        declared = set(pe.required_parameters) | set(pe.optional_parameters)
        f.unexpected_params = sorted(p for p in ev.param_counts if p not in declared) if declared else []
        if f.missing_params or f.partial_params:
            f.status = Status.PARAM_ISSUES
        elif ev.count < pe.expected_minimum_count:
            f.status = Status.BELOW_EXPECTED
        findings.append(f)

    naming: list[NamingIssue] = []
    ghosts: list[GhostEvent] = []
    for ev in observed:
        if ev.name in plan_names or ev.count == 0:
            continue
        target = canon_plan.get(canonical(ev.name))
        if target:
            naming.append(NamingIssue(observed=ev.name, should_be=target, count=ev.count))
        elif ev.name not in GA4_AUTO_EVENTS and not ev.name.startswith("gtm."):
            ghosts.append(GhostEvent(name=ev.name, count=ev.count))
    naming.sort(key=lambda n: -n.count)
    ghosts.sort(key=lambda g: -g.count)

    return AuditReport(findings, naming, ghosts, health_score(findings, naming), source, period)


def health_score(findings: list[EventFinding], naming: list[NamingIssue]) -> int:
    """0–100. Each plan event contributes equally; parameter coverage is partial credit.

    * pass → 1.0
    * below expected volume → 0.75
    * parameter issues → 0.5 × (share of required params fully covered)
    * missing → 0
    * minus 3 points per naming issue (cap 15)
    """
    if not findings:
        return 0
    total = 0.0
    for f in findings:
        if f.status is Status.PASS:
            total += 1.0
        elif f.status is Status.BELOW_EXPECTED:
            total += 0.75
        elif f.status is Status.PARAM_ISSUES:
            req = [p for p in f.plan.required_parameters if p not in f.unverifiable_params]
            bad = len(f.missing_params) + len(f.partial_params)
            total += 0.5 * (1 - bad / len(req)) if req else 0.5
    score = 100 * total / len(findings) - min(15, 3 * len(naming))
    return max(0, min(100, round(score)))
