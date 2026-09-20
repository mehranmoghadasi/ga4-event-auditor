"""Domain models for the GA4 audit."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Events GA4 collects automatically or via Enhanced Measurement; never "ghosts".
GA4_AUTO_EVENTS = frozenset(
    {
        "page_view", "session_start", "first_visit", "user_engagement", "scroll", "click",
        "view_search_results", "video_start", "video_progress", "video_complete",
        "file_download", "form_start", "form_submit", "app_remove", "app_update",
        "screen_view", "os_update", "notification_receive", "notification_open",
        "in_app_purchase", "ad_impression", "app_exception", "app_clear_data",
    }
)


class Status(str, Enum):
    PASS = "pass"
    PARAM_ISSUES = "param_issues"
    BELOW_EXPECTED = "below_expected"
    MISSING = "missing"


@dataclass(frozen=True)
class PlanEvent:
    name: str
    required_parameters: tuple[str, ...] = ()
    optional_parameters: tuple[str, ...] = ()
    expected_minimum_count: int = 1


@dataclass
class ObservedEvent:
    """An event name seen in GA4, with how often each parameter was actually populated."""

    name: str
    count: int = 0
    param_counts: dict[str, int] = field(default_factory=dict)
    # Parameters we could not inspect (API mode without a registered custom dimension).
    unverifiable_params: set[str] = field(default_factory=set)

    def param_coverage(self, param: str) -> float:
        """Share of occurrences where ``param`` was populated (0.0–1.0)."""
        if not self.count:
            return 0.0
        return min(self.param_counts.get(param, 0), self.count) / self.count


@dataclass
class EventFinding:
    plan: PlanEvent
    status: Status
    count: int = 0
    missing_params: list[str] = field(default_factory=list)
    partial_params: dict[str, float] = field(default_factory=dict)  # param → coverage
    unverifiable_params: list[str] = field(default_factory=list)
    unexpected_params: list[str] = field(default_factory=list)


@dataclass
class NamingIssue:
    observed: str
    should_be: str
    count: int


@dataclass
class GhostEvent:
    name: str
    count: int


@dataclass
class AuditReport:
    findings: list[EventFinding]
    naming_issues: list[NamingIssue]
    ghost_events: list[GhostEvent]
    health_score: int
    source: str
    period: str

    def by_status(self, status: Status) -> list[EventFinding]:
        return [f for f in self.findings if f.status is status]
