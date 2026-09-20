from pathlib import Path

from ga4audit.engine import audit, canonical, health_score
from ga4audit.models import ObservedEvent, PlanEvent, Status
from ga4audit.plan import load_plan
from ga4audit.report import render_console, render_markdown, write_all
from ga4audit.sources import demo_events, load_export_csv

FIX = Path(__file__).parent / "fixtures"


# ── plan loading ──────────────────────────────────────────────────────────────

def test_load_plan_json_both_key_styles(tmp_path):
    p = tmp_path / "plan.json"
    p.write_text('{"property_id": "1", "events": [{"name": "purchase", "required_parameters": ["value"]}, {"event_name": "login"}]}')
    events, meta = load_plan(p)
    assert [e.name for e in events] == ["purchase", "login"]
    assert events[0].required_parameters == ("value",) and meta["property_id"] == "1"


def test_load_plan_csv_splits_lists():
    events, _ = load_plan(FIX / "plan.csv")
    assert events[0].required_parameters == ("transaction_id", "value", "currency")
    assert events[1].required_parameters == ("currency", "value") and events[1].expected_minimum_count == 5


# ── canonical naming ──────────────────────────────────────────────────────────

def test_canonical_normalises_variants():
    assert canonical("Add_To_Cart") == canonical("add-to-cart") == canonical("addToCart") == "add_to_cart"


# ── export parsing ────────────────────────────────────────────────────────────

def test_long_export_counts_occurrences_and_param_coverage():
    ev = {e.name: e for e in load_export_csv(FIX / "export_long.csv")}
    assert ev["purchase"].count == 2
    assert ev["purchase"].param_counts["transaction_id"] == 2
    assert ev["purchase"].param_counts["currency"] == 1  # second purchase lacks currency
    assert ev["purchase"].param_coverage("currency") == 0.5
    assert ev["begin_checkout"].param_counts.get("currency") is None


def test_wide_export_uses_count_column():
    ev = {e.name: e for e in load_export_csv(FIX / "export_wide.csv")}
    assert ev["add_to_cart"].count == 400
    assert ev["add_to_cart"].param_coverage("currency") == 0.75
    assert ev["view_item"].param_coverage("items") == 1.0


# ── engine ────────────────────────────────────────────────────────────────────

def test_audit_end_to_end_on_fixture():
    plan, _ = load_plan(FIX / "plan.json")
    r = audit(plan, load_export_csv(FIX / "export_long.csv"), coverage_threshold=0.95)
    by = {f.plan.name: f for f in r.findings}
    assert by["purchase"].status is Status.PARAM_ISSUES and by["purchase"].partial_params == {"currency": 0.5}
    assert by["begin_checkout"].missing_params == ["currency"]
    assert by["add_to_cart"].status is Status.BELOW_EXPECTED  # 1 < 200, params fine
    assert by["generate_lead"].status is Status.MISSING  # only Generate_Lead fired
    assert by["view_item"].status is Status.MISSING
    assert [(n.observed, n.should_be) for n in r.naming_issues] == [("Generate_Lead", "generate_lead")]
    assert [g.name for g in r.ghost_events] == ["checkout_start"]  # page_view is auto-collected


def test_unverifiable_params_do_not_count_as_missing():
    plan = [PlanEvent("purchase", ("value", "currency"))]
    obs = [ObservedEvent("purchase", 100, {"value": 100}, unverifiable_params={"currency"})]
    f = audit(plan, obs).findings[0]
    assert f.status is Status.PASS and f.unverifiable_params == ["currency"]


def test_health_score_bounds_and_partial_credit():
    plan = [PlanEvent("a", ("x", "y")), PlanEvent("b")]
    assert audit(plan, [ObservedEvent("a", 10, {"x": 10, "y": 10}), ObservedEvent("b", 10)]).health_score == 100
    assert audit(plan, []).health_score == 0
    r = audit(plan, [ObservedEvent("a", 10, {"x": 10}), ObservedEvent("b", 10)])  # a: half its params → 0.25
    assert r.health_score == round(100 * (0.25 + 1) / 2)
    assert health_score([], []) == 0


def test_demo_data_exercises_every_bucket():
    plan, _ = load_plan(FIX / "plan.json")
    r = audit(plan, demo_events(plan))
    assert r.by_status(Status.MISSING) and r.by_status(Status.PARAM_ISSUES) and r.naming_issues and r.ghost_events


# ── reports ───────────────────────────────────────────────────────────────────

def test_reports_written(tmp_path):
    plan, _ = load_plan(FIX / "plan.json")
    r = audit(plan, load_export_csv(FIX / "export_long.csv"))
    paths = write_all(r, tmp_path)
    assert all(p.exists() for p in paths.values())
    assert "Health score" in render_console(r, color=False)
    assert "| `purchase` | param_issues |" in render_markdown(r)
    assert "checkout_start,ghost,1" in paths["csv"].read_text()
