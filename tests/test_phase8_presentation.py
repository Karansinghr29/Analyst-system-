"""
Phase 8: the presentation layer.

The architectural rule under test (Phase 8 brief 19): the frontend must never calculate, query
evidence, override trust, select a conflict definition, invent a value, infer causality, bypass
validation, or ask an LLM for a number.

These are tested as properties of the PAYLOAD, not as promises about a frontend. A payload that
carries no formula cannot be used to calculate; a tile with no `value` field cannot render a
headline. The guarantee is structural.
"""
import subprocess
import sys
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.view_models import (ViewModelBuilder, WIDGET_BY_TRUST, WIDGET_KPI,
                                WIDGET_MULTI_DEF, WIDGET_CONFLICT, WIDGET_UNAVAILABLE,
                                CHART_NONE, CHART_MULTI_DEF_BAR, format_value)
from engine import trust_presentation as tp
from engine.gate import TrustGate
from engine.result import NOT_DETERMINABLE_TEXT

_CACHE = {}


@pytest.fixture(scope="module")
def vb(registry):
    return ViewModelBuilder(registry=registry)


@pytest.fixture(scope="module")
def home(vb):
    if "home" not in _CACHE:
        _CACHE["home"] = vb.owner_home()
    return _CACHE["home"]


class TestTrustPresentation:
    def test_every_trust_level_has_an_owner_translation(self):
        for level in ("SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE"):
            p = tp.present(level)
            assert p.owner_label and p.owner_explanation
            assert p.trust_level == level, "the machine state must survive translation"

    def test_owner_labels_avoid_technical_vocabulary(self):
        for p in tp.all_presentations():
            for jargon in ("SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE", "metric_id", "trust_level"):
                assert jargon not in p.owner_label

    def test_headline_permission_matches_the_policy(self):
        assert tp.present("SAFE").headline_permitted
        assert tp.present("DISCLOSE").headline_permitted
        for level in ("SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE"):
            assert not tp.present(level).headline_permitted

    def test_conflicts_are_the_most_prominent(self):
        """A conflict the owner cannot see is a conflict that does not exist for them."""
        assert tp.present("BLOCK").prominence > tp.present("SAFE").prominence
        assert tp.present("SHOW_BOTH").prominence > tp.present("DISCLOSE").prominence

    def test_not_determinable_carries_the_exact_phrase(self):
        assert NOT_DETERMINABLE_TEXT in tp.present("NOT_DETERMINABLE").owner_explanation

    def test_an_unknown_level_is_not_guessed_at(self):
        p = tp.present("SOMETHING_NEW")
        assert not p.headline_permitted
        assert NOT_DETERMINABLE_TEXT in p.owner_explanation


class TestTilePayloads:
    def test_widget_is_chosen_by_trust_not_by_the_author(self, home, registry):
        gate = TrustGate(registry)
        for t in home.all_tiles():
            assert t.widget == WIDGET_BY_TRUST[gate.authorize(t.metric_id).effective_level]

    def test_a_headline_forbidden_tile_carries_no_value(self, home):
        """The structural guarantee: there is nothing for a frontend to render as a headline."""
        blocked = [t for t in home.all_tiles() if not t.headline_permitted]
        assert blocked, "the dashboard should contain conflicted tiles"
        for t in blocked:
            assert t.value is None
            assert t.display_value == ""

    def test_value_and_definitions_are_mutually_exclusive(self, home):
        for t in home.all_tiles():
            assert not (t.value is not None and t.definitions), (
                f"{t.metric_id}: carries both a value and competing definitions, so a frontend "
                f"would have to choose between them")

    def test_a_permitted_headline_is_pre_formatted(self, home):
        """A UI that formats is a UI that can round a figure away from the engine."""
        for t in home.all_tiles():
            if t.headline_permitted and t.value is not None:
                assert t.display_value, f"{t.metric_id}: raw value with no display_value"

    def test_no_payload_carries_a_formula_or_query(self, home):
        forbidden = ("sql", "query", "formula", "expression", "connection", "csv_path",
                     "raw_rows", "aggregation_fn")
        for t in home.all_tiles():
            for key in t.as_dict():
                assert not any(f in key.lower() for f in forbidden), (
                    f"{t.metric_id} exposes {key!r} -- a frontend given a query can compute")

    def test_the_three_conflicted_tiles_are_present(self, home):
        by_id = {t.metric_id: t for t in home.all_tiles()}
        for mid in ("M.AR.001A", "M.OCC.001", "M.PROFIT.001"):
            assert mid in by_id
            assert by_id[mid].headline_permitted is False
            assert len(by_id[mid].definitions) >= 3

    def test_block_offers_no_chart_at_all(self, vb, registry):
        """A bar chart of competing values invites picking the tallest -- choosing by visual
        means rather than by argument."""
        gate = TrustGate(registry)
        for mid in registry.all_ids():
            if gate.authorize(mid).effective_level == "BLOCK":
                assert vb.tile(mid).chart_type == CHART_NONE, mid

    def test_show_both_may_offer_a_comparison_bar(self, vb):
        t = vb.tile("M.OCC.001")
        assert t.chart_type == CHART_MULTI_DEF_BAR

    def test_not_determinable_shows_the_phrase_and_no_chart(self, vb, registry):
        gate = TrustGate(registry)
        found = False
        for mid in registry.all_ids():
            if gate.authorize(mid).effective_level != "NOT_DETERMINABLE":
                continue
            found = True
            t = vb.tile(mid)
            assert t.value is None and t.display_value == ""
            assert NOT_DETERMINABLE_TEXT in t.unavailable_reason
            assert t.chart_type == CHART_NONE
        assert found

    def test_a_degraded_answer_keeps_the_gate_posture(self, vb):
        """M.OCC.005: the conflict is real, its figures are not computable. Showing the
        degraded NOT_DETERMINABLE level would tell the owner the conflict does not exist."""
        t = vb.tile("M.OCC.005")
        assert t.trust["trust_level"] == "SHOW_BOTH"
        assert t.headline_permitted is False
        assert NOT_DETERMINABLE_TEXT in t.unavailable_reason

    def test_unknown_metric_yields_an_unavailable_tile(self, vb):
        t = vb.tile("M.NOPE.001")
        assert t.widget == WIDGET_UNAVAILABLE
        assert NOT_DETERMINABLE_TEXT in t.unavailable_reason


class TestOwnerHome:
    def test_all_sections_populate(self, home):
        assert len(home.business_health) == 8
        assert len(home.operations) == 8
        assert home.risks and home.insights and home.changes
        assert home.decision_queue and home.recommended_actions

    def test_every_tile_maps_to_a_real_metric(self, home, registry):
        for t in home.all_tiles():
            assert t.metric_id in registry

    def test_critical_findings_are_not_buried(self, home):
        """Categorising by trust before severity buried every CRITICAL finding under
        'Definition Conflict', where an owner scanning for urgent problems would not look."""
        critical = [i for i in home.insights if i.category == tp.CAT_CRITICAL]
        assert len(critical) >= 4

    def test_positive_category_is_populated_from_validated_changes(self, home):
        positive = [i for i in home.insights if i.category == tp.CAT_POSITIVE]
        assert positive, "a validated increase exists but no Positive insight was surfaced"
        for i in positive:
            assert NOT_DETERMINABLE_TEXT in i.what_would_change_it, (
                "a Positive change must still state that materiality is undefined")

    def test_opportunity_is_empty_and_that_is_honest(self, home):
        """No opportunity is inferred from a metric merely existing."""
        assert not [i for i in home.insights if i.category == tp.CAT_OPPORTUNITY]

    def test_every_insight_carries_the_required_parts(self, home):
        for i in home.insights:
            assert i.what_happened.strip()
            assert i.why_it_matters.strip()
            assert i.confidence.strip()
            assert i.evidence or i.dq_ids or i.conflict_ids

    def test_changes_declare_materiality_undefined(self, home):
        for c in home.changes:
            assert NOT_DETERMINABLE_TEXT in c.materiality_note

    def test_incomplete_periods_are_named(self, home):
        assert any("excluded as incomplete" in c.coverage_note for c in home.changes)

    def test_trust_summary_covers_every_metric(self, home, registry):
        assert sum(v["count"] for v in home.trust_summary.values()) == len(registry.all_ids())

    def test_home_is_deterministic(self, registry):
        a = ViewModelBuilder(registry=registry).owner_home()
        b = ViewModelBuilder(registry=registry).owner_home()
        assert [t.metric_id for t in a.all_tiles()] == [t.metric_id for t in b.all_tiles()]
        assert [i.insight_id for i in a.insights] == [i.insight_id for i in b.insights]


class TestMetricDetailAndConflict:
    def test_metric_detail_carries_every_required_section(self, vb):
        d = vb.metric_detail("M.REV.001")
        for key in ("business_definition", "trust", "calculation", "evidence", "validation",
                    "related_metrics", "conflicts", "dq_issues", "recommended_questions"):
            assert key in d, key
        assert d["evidence"]

    def test_related_metrics_are_documented_edges_only(self, vb, registry):
        d = vb.metric_detail("M.PNL.001")
        documented = set(registry.get("M.PNL.001").dependency_metrics)
        for m in d["related_metrics"]:
            assert m in documented

    def test_conflict_view_never_picks_a_winner(self, vb, registry):
        gate = TrustGate(registry)
        for mid in registry.all_ids():
            if gate.authorize(mid).effective_level not in ("SHOW_BOTH", "BLOCK"):
                continue
            cv = vb.conflict_view(mid)
            assert cv["headline_permitted"] is False
            assert "business decision" in cv["which_should_we_use"]
            assert "not the system" in cv["resolution_owner"]

    def test_conflict_view_lists_every_definition(self, vb):
        cv = vb.conflict_view("M.AR.001A")
        assert len(cv["definitions"]) == 4
        for d in cv["definitions"]:
            for key in ("label", "value", "source", "time_semantics", "calculation", "trust"):
                assert key in d

    def test_an_uncomputable_conflict_says_so(self, vb):
        cv = vb.conflict_view("M.OCC.005")
        assert cv["definitions_computable"] is False
        assert NOT_DETERMINABLE_TEXT in cv["note"]

    def test_unknown_metric_detail_is_unavailable(self, vb):
        d = vb.metric_detail("M.NOPE.001")
        assert d["available"] is False
        assert NOT_DETERMINABLE_TEXT in d["unavailable_reason"]


class TestDataQualityCenterAndWorkspaces:
    def test_dq_center_groups_by_recorded_severity(self, vb):
        c = vb.data_quality_center()
        assert c["total"] > 0
        sevs = [s["severity"] for s in c["severities"]]
        assert "CRITICAL" in sevs
        assert sevs == sorted(sevs, key=lambda s: (
            "CRITICAL HIGH MEDIUM LOW INFORMATIONAL UNVERIFIED".split().index(s)))

    def test_dq_findings_link_to_affected_metrics(self, vb, registry):
        c = vb.data_quality_center()
        for sec in c["severities"]:
            for issue in sec["issues"]:
                for m in issue["affected_metrics"]:
                    assert m in registry

    def test_every_role_has_a_workspace(self, vb):
        from engine import analyst_roles
        for r in analyst_roles.all_roles():
            ws = vb.role_workspace(r.role_id)
            assert ws["available"] and ws["tiles"]

    def test_workspaces_share_one_definition_per_metric(self, vb, registry):
        from engine import analyst_roles
        titles = {}
        for r in analyst_roles.all_roles():
            for t in vb.role_workspace(r.role_id)["tiles"]:
                titles.setdefault(t["metric_id"], set()).add(t["title"])
        for mid, names in titles.items():
            assert len(names) == 1, f"{mid}: workspaces disagree on the title {names}"

    def test_conflicted_metrics_stay_conflicted_in_every_workspace(self, vb, registry):
        from engine import analyst_roles
        gate = TrustGate(registry)
        for r in analyst_roles.all_roles():
            for t in vb.role_workspace(r.role_id)["tiles"]:
                lvl = gate.authorize(t["metric_id"]).effective_level
                if lvl in ("SHOW_BOTH", "BLOCK"):
                    assert t["headline_permitted"] is False, f"{r.role_id}/{t['metric_id']}"

    def test_unknown_role_is_refused(self, vb):
        assert vb.role_workspace("marketing_analyst")["available"] is False


class TestFormatting:
    def test_currency_is_formatted_server_side(self):
        assert format_value(72705593.43, "INR") == "₹72,705,593.43"

    def test_counts_render_without_decimals(self):
        assert format_value(168, "allotments") == "168"

    def test_none_renders_empty_not_zero(self):
        assert format_value(None) == ""


class TestValidatorAndIntegrity:
    def test_the_phase8_validator_passes(self):
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts",
                                          "validate_phase8_consistency.py")],
            capture_output=True, text=True, cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        assert r.returncode == 0, r.stdout[-4000:]
        assert "No inconsistency" in r.stdout

    def test_source_csvs_are_byte_identical(self):
        import csv as _csv
        import hashlib
        with open(os.path.join(ROOT, "evidence", "file_manifest.csv"),
                  encoding="utf-8-sig") as f:
            rows = list(_csv.DictReader(f))
        h = hashlib.sha256()
        for r in rows:
            with open(os.path.join(ROOT, r["file"]), "rb") as fh:
                h.update(fh.read())
        assert h.hexdigest() == (
            "aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26")
