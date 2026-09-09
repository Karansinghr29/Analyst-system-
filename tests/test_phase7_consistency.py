"""
Phase 7: the blueprint must stay consistent with the live Phase 1-6 system.

A specification phase produces prose, and prose drifts. These tests are the guard that makes the
blueprint falsifiable: a document that names a metric the registry lacks, asserts a trust level
the gate does not assign, or permits a rendering the trust policy forbids fails here rather than
being discovered when someone builds against it.
"""
import csv
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine import analyst_roles

PHASE7_DOCS = (
    "phase7_product_architecture.md", "owner_experience_spec.md",
    "role_based_analytics_spec.md", "bi_dashboard_spec.md",
    "proactive_insight_system_spec.md", "decision_support_spec.md",
    "business_analyst_ai_spec.md", "conversation_dashboard_integration_spec.md",
    "production_ai_architecture.md", "powerbi_analytics_mapping.md",
    "business_question_matrix.md", "final_system_capabilities.md",
    "phase7_implementation_roadmap.md",
)

PHASE7_REGISTRIES = ("owner_dashboard_registry.csv", "role_view_registry.csv",
                     "conflict_disclosure_registry.csv")

NOT_DET = "Not determinable from exported evidence."


def _rows(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestDeliverables:
    @pytest.mark.parametrize("doc", PHASE7_DOCS)
    def test_every_declared_document_exists(self, doc):
        assert os.path.exists(os.path.join(ROOT, doc)), f"{doc} is a declared deliverable"

    @pytest.mark.parametrize("name", PHASE7_REGISTRIES)
    def test_every_declared_registry_exists(self, name):
        assert os.path.exists(os.path.join(ROOT, name))

    def test_the_consistency_validator_passes(self):
        """The whole blueprint, checked end to end against the live system."""
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts",
                                          "validate_phase7_consistency.py")],
            capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, r.stdout[-3000:]
        assert "No inconsistency" in r.stdout


class TestDashboardRegistry:
    def test_every_tile_is_a_registry_metric(self, registry):
        for row in _rows("owner_dashboard_registry.csv"):
            assert row["metric_id"] in registry, (
                f"dashboard tile {row['metric_id']} is not a semantic metric -- the dashboard "
                f"may not invent a KPI")

    def test_every_tile_trust_matches_the_gate(self, registry):
        gate = TrustGate(registry)
        for row in _rows("owner_dashboard_registry.csv"):
            assert row["trust_level"] == gate.authorize(row["metric_id"]).effective_level

    def test_conflicted_tiles_forbid_a_headline(self, registry):
        conflicted = [r for r in _rows("owner_dashboard_registry.csv")
                      if r["trust_level"] in ("SHOW_BOTH", "BLOCK")]
        assert conflicted, "no conflicted tile present -- the dashboard should contain three"
        for row in conflicted:
            assert row["headline_permitted"] == "False", (
                f"{row['metric_id']} permits a headline it must not")
            assert int(row["definition_count"]) >= 2

    def test_the_three_known_conflicted_tiles_are_present(self):
        rows = {r["metric_id"]: r for r in _rows("owner_dashboard_registry.csv")}
        for mid in ("M.AR.001A", "M.OCC.001", "M.PROFIT.001"):
            assert mid in rows
            assert rows[mid]["headline_permitted"] == "False"

    def test_disclose_tiles_render_their_caveat(self):
        for row in _rows("owner_dashboard_registry.csv"):
            if row["trust_level"] == "DISCLOSE":
                assert row["caveat"].strip(), f"{row['metric_id']}: DISCLOSE with no caveat"

    def test_block_tiles_name_their_conflict(self):
        for row in _rows("owner_dashboard_registry.csv"):
            if row["trust_level"] == "BLOCK":
                assert row["conflict_ids"].strip()


class TestRoleViewRegistry:
    def test_all_nine_roles_are_present(self):
        roles = {r["role_id"] for r in _rows("role_view_registry.csv")}
        assert roles == set(analyst_roles.ALL_ROLES)

    def test_every_view_matches_the_gate(self, registry):
        gate = TrustGate(registry)
        for row in _rows("role_view_registry.csv"):
            assert row["trust_level"] == gate.authorize(row["metric_id"]).effective_level, (
                f"{row['role_id']}/{row['metric_id']}")

    def test_all_roles_share_one_definition_per_metric(self, registry):
        """The central guarantee: nine lenses, one semantic layer."""
        by_metric = {}
        for row in _rows("role_view_registry.csv"):
            by_metric.setdefault(row["metric_id"], set()).add(row["metric_name"])
        for mid, names in by_metric.items():
            assert len(names) == 1, f"{mid}: roles disagree on the metric name {names}"
            assert names.pop() == registry.get(mid).semantic_name

    def test_conflicted_views_forbid_selecting_a_definition(self):
        for row in _rows("role_view_registry.csv"):
            if row["trust_level"] in ("SHOW_BOTH", "BLOCK"):
                assert row["headline_permitted"] == "False"
                concl = row["permitted_conclusion"].lower()
                assert "may not select" in concl or "may not state" in concl

    def test_every_view_states_what_it_must_never_claim(self):
        for row in _rows("role_view_registry.csv"):
            assert row["must_never_claim"].strip()

    def test_no_role_view_is_looser_than_the_trust_policy(self, registry):
        gate = TrustGate(registry)
        for row in _rows("role_view_registry.csv"):
            trust = gate.authorize(row["metric_id"]).effective_level
            permitted = row["headline_permitted"] == "True"
            assert permitted == (trust in ("SAFE", "DISCLOSE"))


class TestConflictDisclosureRegistry:
    def test_every_conflicted_metric_is_registered(self, registry):
        gate = TrustGate(registry)
        listed = {r["metric_id"] for r in _rows("conflict_disclosure_registry.csv")}
        for mid in registry.all_ids():
            if gate.authorize(mid).effective_level in ("SHOW_BOTH", "BLOCK"):
                assert mid in listed, (
                    f"{mid} is conflicted but unregistered -- an unregistered conflict can be "
                    f"dropped from a surface without anything noticing")

    def test_no_conflict_permits_a_headline_anywhere(self):
        for row in _rows("conflict_disclosure_registry.csv"):
            assert row["headline_permitted_anywhere"] == "False"

    def test_every_conflict_must_appear_on_every_surface(self):
        required = ("owner_dashboard", "role_views", "bi_cards", "executive_summary",
                    "insight_feed", "decision_queue", "conversation_answers")
        for row in _rows("conflict_disclosure_registry.csv"):
            for surface in required:
                assert surface in row["must_appear_on"], (
                    f"{row['metric_id']} not required on {surface}")

    def test_resolution_is_an_owner_decision(self):
        for row in _rows("conflict_disclosure_registry.csv"):
            assert "owner" in row["resolution_owner"].lower()
            assert "not the system" in row["resolution_owner"].lower()

    def test_an_uncomputable_conflict_says_so_with_the_exact_phrase(self):
        """M.OCC.005 carries a real conflict whose definitions are not computable in the current
        engine. The registry must say so rather than imply two comparable figures exist."""
        uncomputable = [r for r in _rows("conflict_disclosure_registry.csv")
                        if r["definitions_computable"] == "False"]
        for row in uncomputable:
            assert NOT_DET in row["resolution_note"]


class TestSourceIntegrity:
    def test_source_csvs_are_byte_identical(self):
        """Phase 7 is a specification phase: it must not have touched the evidence."""
        import hashlib
        manifest = os.path.join(ROOT, "evidence", "file_manifest.csv")
        with open(manifest, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        h = hashlib.sha256()
        for r in rows:
            with open(os.path.join(ROOT, r["file"]), "rb") as fh:
                h.update(fh.read())
        assert h.hexdigest() == (
            "aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26")
        assert len(rows) == 253

    def test_the_semantic_registry_has_not_drifted(self, registry):
        from engine.semantic_registry import cross_check_against_legacy_registry
        assert cross_check_against_legacy_registry(registry) == []

    def test_the_registry_still_holds_49_metrics(self, registry):
        assert len(registry.all_ids()) == 50
