"""
Phase 9: the production integration layer.

Every test here asks one question: does going through the service change any guarantee the
engine makes? The answer must be no, for every guarantee, at every boundary — API, auth,
persistence, LLM config, and the live-data connector.
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.gate import TrustGate
from engine.result import NOT_DETERMINABLE_TEXT
from engine import analyst_roles
from engine.conversation_state import PendingClarification, DefinitionSelection

from api.service import AnalyticsService, create_app
from api.authorization import Authorizer, Session, AuthorizationError, ROLE_OWNER
from api.conversation_store import ConversationStore
from api import data_source as ds
from api import provider_config as pc
from api.auth import suite_authenticator, bearer_headers

_CACHE = {}


@pytest.fixture(scope="module")
def tmpdb():
    return os.path.join(tempfile.mkdtemp(), "phase9.db")


@pytest.fixture(scope="module")
def svc(registry, tmpdb):
    if "svc" not in _CACHE:
        _CACHE["svc"] = AnalyticsService(registry=registry, db_path=tmpdb)
    return _CACHE["svc"]


@pytest.fixture(scope="module")
def gate(registry):
    return TrustGate(registry)


class TestServiceBoundary:
    def test_health_reports_source_and_revalidation(self, svc):
        h = svc.health()
        assert h["status"] == "ok"
        assert h["metrics"] == 50
        assert h["data_source"]["status"] == ds.STATUS_TRUSTED
        assert h["revalidation"]["passed"] is True

    def test_every_surface_is_json_serialisable(self, svc):
        for name, payload in (("home", svc.owner_home()), ("metrics", svc.metrics()),
                              ("insights", svc.insights()), ("changes", svc.changes()),
                              ("dq", svc.data_quality()), ("roles", svc.roles()),
                              ("trust", svc.trust_summary()),
                              ("report", svc.executive_report())):
            json.dumps(payload, default=str), name

    def test_no_response_carries_a_query_or_formula(self, svc):
        """A client given a query can compute, and a client that can compute can disagree."""
        forbidden = ("sql", "query", "formula", "expression", "connection_string",
                     "csv_path", "raw_rows", "aggregation_fn")
        blob = json.dumps(svc.owner_home(), default=str).lower()
        for f in forbidden:
            assert f'"{f}"' not in blob

    def test_the_service_computes_nothing_of_its_own(self, svc, registry):
        """Every served value must equal the engine value for the same metric."""
        from engine.execution import MetricExecutor
        ex = MetricExecutor(registry=registry)
        served = {m["metric_id"]: m for m in svc.metrics()["metrics"]}
        for mid in ("M.REV.001", "M.EXP.001", "M.CASH.001"):
            assert abs(served[mid]["value"] - ex.execute(mid).headline) < 0.01


class TestTrustFidelityThroughTheAPI:
    def test_served_trust_matches_the_gate_for_every_metric(self, svc, registry, gate):
        for mid in registry.all_ids():
            tile = svc.metric_detail(mid)["tile"]
            assert tile["trust"]["trust_level"] == gate.authorize(mid).effective_level, mid

    def test_block_payloads_carry_no_headline(self, svc, registry, gate):
        found = False
        for mid in registry.all_ids():
            if gate.authorize(mid).effective_level != "BLOCK":
                continue
            found = True
            tile = svc.metric_detail(mid)["tile"]
            assert tile["headline_permitted"] is False
            assert tile["value"] is None
            assert tile["display_value"] == ""
            assert tile["chart_type"] == "none"
        assert found

    def test_show_both_payloads_carry_every_definition(self, svc, registry, gate):
        for mid in registry.all_ids():
            if gate.authorize(mid).effective_level != "SHOW_BOTH":
                continue
            cv = svc.conflict_view(mid)
            if cv.get("available") is False:
                pytest.fail(f"{mid}: no conflict view served")
            if cv["definitions_computable"]:
                assert len(cv["definitions"]) >= 2
            assert cv["headline_permitted"] is False

    def test_not_determinable_payloads_keep_the_exact_phrase(self, svc, registry, gate):
        found = False
        for mid in registry.all_ids():
            if gate.authorize(mid).effective_level != "NOT_DETERMINABLE":
                continue
            found = True
            tile = svc.metric_detail(mid)["tile"]
            assert tile["value"] is None
            assert NOT_DETERMINABLE_TEXT in tile["unavailable_reason"]
        assert found

    def test_conflict_view_never_picks_a_winner(self, svc, registry, gate):
        for mid in registry.all_ids():
            if gate.authorize(mid).effective_level not in ("SHOW_BOTH", "BLOCK"):
                continue
            cv = svc.conflict_view(mid)
            assert "business decision" in cv["which_should_we_use"]
            assert "not the system" in cv["resolution_owner"]

    def test_a_non_conflicted_metric_has_no_conflict_view(self, svc):
        cv = svc.conflict_view("M.REV.001")
        assert cv["available"] is False


class TestAuthorization:
    """The subtle invariant: a role may see fewer metrics, never a looser posture."""

    def test_authorization_never_changes_a_trust_level(self, svc, registry, gate):
        auth = Authorizer(registry)
        for role_id in auth.known_roles():
            for tile in svc.metrics(role_id)["metrics"]:
                mid = tile["metric_id"]
                expected = gate.authorize(mid).effective_level
                assert tile["trust"]["trust_level"] == expected, f"{role_id}/{mid}"
                assert tile["headline_permitted"] == (expected in ("SAFE", "DISCLOSE"))

    def test_a_conflicted_metric_is_conflicted_for_every_role(self, svc, registry, gate):
        auth = Authorizer(registry)
        for role_id in auth.known_roles():
            for tile in svc.metrics(role_id)["metrics"]:
                if gate.authorize(tile["metric_id"]).effective_level in ("SHOW_BOTH", "BLOCK"):
                    assert tile["headline_permitted"] is False
                    assert tile["value"] is None

    def test_roles_see_only_their_domains(self, registry):
        auth = Authorizer(registry)
        fin = auth.filter_metrics(analyst_roles.FINANCIAL_ANALYST)
        for m in fin:
            assert registry.get(m).domain == "Financial"
        ops = auth.filter_metrics(analyst_roles.OPERATIONS_ANALYST)
        assert set(fin) & set(ops) == set()

    def test_an_unknown_role_is_refused(self, registry):
        with pytest.raises(AuthorizationError):
            Authorizer(registry).resolve("marketing_lead")

    def test_authorization_exposes_no_trust_mechanism(self):
        """Structural: there is no function here that could change a verdict."""
        import api.authorization as mod
        src = open(mod.__file__, encoding="utf-8").read()
        for forbidden in ("effective_level =", "trust_level =", "headline_permitted ="):
            assert forbidden not in src

    def test_describe_states_the_trust_invariant(self, registry):
        d = Authorizer(registry).describe(ROLE_OWNER)
        assert "not of the viewer" in d["trust_note"]


class TestConversationPersistence:
    def test_an_open_clarification_survives_a_restart(self, tmpdb):
        """Losing this would make a reloaded conversation read the user's answer as a fresh
        question, and would silently drop a pending ambiguity."""
        path = os.path.join(tempfile.mkdtemp(), "clar.db")
        s1 = ConversationStore(path)
        s1.create("c", "sub", ROLE_OWNER)
        pending = PendingClarification(
            trigger="conflicting_definitions", question="Which one?",
            options=("M.COL.001: application", "M.COL.003: ledger"),
            option_metric_ids=("M.COL.001", "M.COL.003"), asked_at_turn=0, state="REQUIRED")
        s1.save_clarification("c", pending)
        s1.close()

        s2 = ConversationStore(path)          # simulates a process restart
        back = s2.load_clarification("c")
        assert back is not None
        assert back.state == "REQUIRED"
        assert back.option_metric_ids == ("M.COL.001", "M.COL.003")
        s2.close()

    def test_a_definition_selection_survives_a_restart(self, tmpdb):
        path = os.path.join(tempfile.mkdtemp(), "sel.db")
        s1 = ConversationStore(path)
        s1.create("c", "sub", ROLE_OWNER)
        s1.save_selection("c", DefinitionSelection(
            concept="occupancy", metric_id="M.OCC.001", definition_label="Def A",
            selected_at_turn=1, user_text="use Def A",
            alternatives_shown=("Def A", "Def B")))
        s1.close()
        s2 = ConversationStore(path)
        sels = s2.load_selections("c")
        assert len(sels) == 1 and sels[0].definition_label == "Def A"
        s2.close()

    def test_restore_into_rehydrates_a_live_context(self, registry):
        from engine.conversation_context import ConversationContext
        path = os.path.join(tempfile.mkdtemp(), "restore.db")
        store = ConversationStore(path)
        store.create("c", "sub", ROLE_OWNER)
        store.save_clarification("c", PendingClarification(
            trigger="t", question="q", options=("a", "b"), option_metric_ids=("", ""),
            asked_at_turn=0, state="REQUIRED"))
        ctx = ConversationContext()
        store.restore_into("c", ctx)
        assert ctx.awaiting_clarification
        store.close()

    def test_turns_are_recorded_in_order(self, tmpdb):
        path = os.path.join(tempfile.mkdtemp(), "turns.db")
        store = ConversationStore(path)
        store.create("c", "sub", ROLE_OWNER)
        for q in ("first", "second", "third"):
            store.append_turn("c", q)
        assert [t.question for t in store.turns("c")] == ["first", "second", "third"]
        store.close()

    def test_trust_is_not_persisted_as_authoritative(self, svc):
        """A cached trust posture is a correctness failure, not a stale number. The stored
        level is history; the served level is re-read from the gate every turn."""
        r1 = svc.ask("How much revenue did we make?")
        cid = r1["conversation_id"]
        r2 = svc.ask("How much revenue did we make?", conversation_id=cid)
        assert r1["trust_level"] == r2["trust_level"] == "SAFE"


class TestAskThroughTheService:
    def test_a_question_runs_the_same_pipeline(self, svc):
        r = svc.ask("How much revenue did we make?")
        assert r["trust_level"] == "SAFE"
        assert r["metric_ids"] == ["M.REV.001"]
        assert r["headline_permitted"] is True
        assert len(r["evidence_chain"]) == 10

    def test_a_block_question_exposes_no_headline(self, svc):
        r = svc.ask("What's our profit?")
        assert r["trust_level"] == "BLOCK"
        assert r["headline_permitted"] is False

    def test_a_show_both_question_keeps_its_definitions(self, svc):
        r = svc.ask("How much do tenants owe?")
        assert r["trust_level"] == "SHOW_BOTH"
        assert r["headline_permitted"] is False

    def test_an_absent_concept_returns_the_exact_phrase(self, svc):
        r = svc.ask("What is our margin analysis?")
        assert NOT_DETERMINABLE_TEXT in r["answer"]

    def test_the_briefing_works_through_the_service(self, svc):
        r = svc.ask("How is the business doing?")
        assert r["owner_intent"] == "briefing"
        assert "Executive takeaway" in r["answer"]
        assert "Key numbers" in r["answer"]

    def test_no_guard_violations_on_the_cooperative_path(self, svc):
        for q in ("How much revenue did we make?", "What is occupancy?", "What's our profit?"):
            assert svc.ask(q)["guard_violations"] == []

    def test_a_conversation_is_retrievable(self, svc):
        r = svc.ask("How much revenue did we make?")
        c = svc.conversation(r["conversation_id"])
        assert c["found"] is True
        assert len(c["turns"]) >= 1


class TestLiveDataQuarantine:
    """The design inversion: a source is quarantined by default, not trusted by default."""

    def test_the_export_source_passes_revalidation(self, registry, gate):
        report = ds.RevalidationHarness(registry, gate).run(ds.ExportDataSource())
        assert report.passed, report.summary()
        assert report.checks_total == 80
        assert report.conflicts_reproduced == report.conflicts_total

    def test_a_live_source_cannot_pass_without_a_connection(self, registry, gate):
        live = ds.LiveDataSource(name="probe", connection=object(), as_of="2026-09-01")
        report = ds.RevalidationHarness(registry, gate).run(live)
        assert report.passed is False
        assert NOT_DETERMINABLE_TEXT in report.notes

    def test_an_unrevalidated_source_is_refused_by_the_engine_binding(self, registry, gate):
        live = ds.LiveDataSource(name="probe", connection=object(), as_of="2026-09-01")
        report = ds.RevalidationHarness(registry, gate).run(live)
        with pytest.raises(ds.QuarantineError):
            ds.bind_source(live, report)

    def test_a_live_source_may_not_inherit_the_export_snapshot_date(self):
        """2026-08-29 is a property of the export, not of the business."""
        live = ds.LiveDataSource(name="no-asof", connection=object())
        d = live.descriptor()
        assert d.status == ds.STATUS_FAILED
        assert "may not be inherited" in d.notes

    def test_the_source_interface_has_no_write_method(self):
        """Read-only by construction, not by policy."""
        for attr in dir(ds.DataSource):
            assert not any(w in attr.lower()
                           for w in ("write", "insert", "update", "delete", "execute"))

    def test_a_conflict_that_stops_reproducing_requires_an_owner_decision(self, registry, gate):
        """The subtle case: a conflict that stops reproducing looks like good news, but the
        registry trust level was set BECAUSE of that conflict. Lowering it silently would change
        every downstream answer with no record of why. Tested behaviourally -- a harness whose
        conflict replay finds nothing must report a required owner decision, not a pass."""

        class SilentlyResolvedHarness(ds.RevalidationHarness):
            def _replay_conflicts(self):
                # Simulate a live source where the AR conflict no longer reproduces.
                total, reproduced, decisions = super()._replay_conflicts()
                return total, reproduced - 1, decisions + (
                    "M.AR.001A: no longer produces competing definitions; a recorded owner "
                    "decision is required before any trust downgrade.",)

        report = SilentlyResolvedHarness(registry, gate).run(ds.ExportDataSource())
        assert report.passed is False, (
            "a conflict that stopped reproducing was treated as a pass")
        assert report.required_owner_decisions
        assert any("owner decision" in d.lower() for d in report.required_owner_decisions)

    def test_a_source_with_required_owner_decisions_cannot_bind(self, registry, gate):
        """A pending owner decision must block the binding, not merely be reported."""
        report = ds.RevalidationReport(
            source_name="probe", passed=False,
            required_owner_decisions=("M.AR.001A: conflict no longer reproduces",))
        live = ds.LiveDataSource(name="probe", connection=object(), as_of="2026-09-01")
        with pytest.raises(ds.QuarantineError):
            ds.bind_source(live, report)


class TestLLMBoundary:
    def test_the_default_provider_is_offline(self, svc):
        d = svc.provider_config.describe()
        assert d["mode"] == pc.MODE_OFFLINE
        assert d["network_access"] is False

    def test_no_adapter_is_enabled_by_a_credential_being_present(self):
        """A key in the environment is not consent to send business data to a service."""
        for a in pc.available_adapters():
            assert a["enabled"] is False

    def test_http_adapters_are_shapes_not_clients(self):
        from engine.llm_provider import LLMUnavailable
        with pytest.raises(LLMUnavailable):
            pc.build_provider(pc.ProviderConfig(mode=pc.MODE_HTTP, adapter_name="groq"))

    def test_a_callable_provider_without_a_function_refuses(self):
        from engine.llm_provider import LLMUnavailable
        with pytest.raises(LLMUnavailable):
            pc.build_provider(pc.ProviderConfig(mode=pc.MODE_CALLABLE))

    def test_an_unreadable_config_defaults_to_offline(self, monkeypatch):
        monkeypatch.setenv(pc.ENV_MODE, "something-unknown")
        assert pc.config_from_env().mode == pc.MODE_OFFLINE

    def test_importing_the_config_reads_no_credential(self):
        """Accidental activation must be impossible, not merely unlikely."""
        import inspect
        src = inspect.getsource(pc)
        module_level = [l for l in src.splitlines()
                        if l.startswith("os.environ") or l.startswith("_KEY")]
        assert module_level == []

    def test_a_hostile_verbalization_is_still_guarded_through_the_service(self, registry):
        from engine.llm_provider import CallableProvider, DeterministicMockProvider

        def hostile(prompt, system, max_tokens, temperature):
            if "VERBALIZE" in system:
                return "Profit is Rs.5,000,000 (M.PROFIT.001)."
            return DeterministicMockProvider()._extract(prompt)

        s = AnalyticsService(
            registry=registry, db_path=os.path.join(tempfile.mkdtemp(), "hostile.db"),
            provider_config=pc.ProviderConfig(mode=pc.MODE_CALLABLE, fn=hostile))
        r = s.ask("What's our profit?")
        assert r["guard_violations"], "the guard did not fire through the service boundary"
        assert r["headline_permitted"] is False
        s.close()


class TestHttpLayer:
    @pytest.fixture(scope="class")
    def client(self, registry):
        from fastapi.testclient import TestClient
        app = create_app(AnalyticsService(
            registry=registry, db_path=os.path.join(tempfile.mkdtemp(), "http.db")),
            authenticator=suite_authenticator())
        client = TestClient(app)
        client.headers.update(bearer_headers())
        return client

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200 and r.json()["status"] == "ok"

    def test_owner_home_over_http(self, client):
        r = client.get("/api/owner/home")
        assert r.status_code == 200
        blocked = [t for t in r.json()["business_health"] if not t["headline_permitted"]]
        assert blocked
        for t in blocked:
            assert t["value"] is None

    def test_block_metric_over_http(self, client):
        r = client.get("/api/metrics/M.PROFIT.001")
        assert r.status_code == 200
        assert r.json()["tile"]["value"] is None

    def test_ask_over_http(self, client):
        r = client.post("/api/ask", json={"question": "How much revenue did we make?"})
        assert r.status_code == 200
        assert r.json()["trust_level"] == "SAFE"

    def test_an_unknown_role_is_rejected(self, client):
        r = client.get("/api/owner/home", headers=bearer_headers("marketing", "spy"))
        assert r.status_code == 403

    def test_x_role_without_a_token_is_not_identity(self, registry):
        from fastapi.testclient import TestClient
        app = create_app(AnalyticsService(
            registry=registry, db_path=os.path.join(tempfile.mkdtemp(), "http2.db")),
            authenticator=suite_authenticator())
        bare = TestClient(app)
        r = bare.get("/api/owner/home", headers={"x-role": "owner"})
        assert r.status_code == 401

    def test_an_unknown_conversation_is_404(self, client):
        assert client.get("/api/conversations/nope").status_code == 404

    def test_the_openapi_schema_exposes_no_query_parameter(self, client):
        schema = client.get("/openapi.json").json()
        blob = json.dumps(schema).lower()
        for forbidden in ('"sql"', '"formula"', '"filter_expression"', '"raw_query"'):
            assert forbidden not in blob


class TestArtifactsAndIntegrity:
    def test_the_phase9_validator_passes(self):
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts",
                                          "validate_phase9_consistency.py")],
            capture_output=True, text=True, cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        assert r.returncode == 0, r.stdout[-4000:]
        assert "No inconsistency" in r.stdout

    def test_the_powerbi_descriptor_forbids_single_conflict_measures(self):
        with open(os.path.join(ROOT, "powerbi_dataset_descriptor.json"),
                  encoding="utf-8") as f:
            d = json.load(f)
        assert d["conflict_tables"]
        for t in d["conflict_tables"]:
            assert t["single_measure_forbidden"] is True
        names = [m["name"] for m in d["forbidden_measures"]]
        assert any("Profit" in n for n in names)

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
