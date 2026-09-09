"""
Phase 11: production activation — auth, live-data quarantine, LLM enable gate,
security, observability. None of these tests send traffic to a live database or a
live model.
"""
import json
import os
import tempfile

import pytest

from engine.gate import TrustGate
from engine.result import NOT_DETERMINABLE_TEXT
from engine import analyst_roles

from api.service import AnalyticsService, create_app
from api.authorization import ROLE_OWNER
from api import data_source as ds
from api import provider_config as pc
from api.auth import (FailClosedAuthenticator, AuthenticationError, mint_token,
                      suite_authenticator, bearer_headers, TEST_SECRET, hmac_authenticator,
                      BearerAuthenticator, HmacVerifier)
from api.security import RateLimiter, sanitize_error, contains_secret_material
from api.live_connector import _WRITE_SQL, relation_from_logical, PostgresReadOnlyTransport


@pytest.fixture
def tmpdb():
    return os.path.join(tempfile.mkdtemp(), "p11.db")


@pytest.fixture
def svc(registry, tmpdb):
    return AnalyticsService(registry=registry, db_path=tmpdb,
                            authenticator=suite_authenticator())


@pytest.fixture
def client(registry, tmpdb):
    from fastapi.testclient import TestClient
    app = create_app(AnalyticsService(registry=registry, db_path=tmpdb,
                                      authenticator=suite_authenticator()),
                     authenticator=suite_authenticator(),
                     rate_limiter=RateLimiter(disabled=True))
    c = TestClient(app)
    c.headers.update(bearer_headers())
    return c


class TestAuthenticationEnforced:
    def test_api_without_a_token_is_401(self, registry, tmpdb):
        from fastapi.testclient import TestClient
        app = create_app(AnalyticsService(registry=registry, db_path=tmpdb,
                                          authenticator=suite_authenticator()),
                         authenticator=suite_authenticator())
        r = TestClient(app).get("/api/owner/home")
        assert r.status_code == 401

    def test_x_role_is_not_identity(self, registry, tmpdb):
        from fastapi.testclient import TestClient
        app = create_app(AnalyticsService(registry=registry, db_path=tmpdb,
                                          authenticator=suite_authenticator()),
                         authenticator=suite_authenticator())
        r = TestClient(app).get("/api/owner/home", headers={"x-role": "owner"})
        assert r.status_code == 401

    def test_health_is_public(self, client):
        # drop auth for this call
        r = client.get("/health", headers={"Authorization": ""})
        # TestClient may still send fixture headers; construct a bare client
        from fastapi.testclient import TestClient
        bare = TestClient(client.app)
        h = bare.get("/health")
        assert h.status_code == 200
        body = h.json()
        assert body["auth"]["enforced"] is True
        assert "remaining_requirement" in body["auth"] or body["auth"]["status"] in (
            "TRUSTED", "QUARANTINED")

    def test_fail_closed_authenticator_always_rejects(self):
        with pytest.raises(AuthenticationError):
            FailClosedAuthenticator().authenticate({"Authorization": "Bearer x"})

    def test_unknown_role_in_a_valid_token_is_403(self, client):
        r = client.get("/api/metrics", headers=bearer_headers("not_a_role", "x"))
        assert r.status_code == 403

    def test_expired_token_is_401(self, registry, tmpdb):
        from fastapi.testclient import TestClient
        app = create_app(AnalyticsService(registry=registry, db_path=tmpdb,
                                          authenticator=suite_authenticator()),
                         authenticator=suite_authenticator())
        token = mint_token(TEST_SECRET, "owner", ROLE_OWNER, ttl_seconds=-10)
        r = TestClient(app).get("/api/metrics",
                                headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401


class TestAuthorizationDoesNotChangeTrust:
    def test_filtered_home_keeps_gate_posture(self, svc, registry):
        gate = TrustGate(registry)
        fin = analyst_roles.FINANCIAL_ANALYST
        home = svc.owner_home(fin)
        for t in home["business_health"] + home["operations"] + home["risks"]:
            expected = gate.authorize(t["metric_id"]).effective_level
            assert t["trust"]["trust_level"] == expected

    def test_operations_metric_absent_for_financial_role(self, svc):
        vis = set(svc.authorizer.filter_metrics(analyst_roles.FINANCIAL_ANALYST))
        assert "M.OCC.001" not in vis
        detail = svc.metric_detail("M.OCC.001", analyst_roles.FINANCIAL_ANALYST)
        assert detail["available"] is False
        # trust of the metric itself is unchanged
        assert svc.gate.authorize("M.OCC.001").effective_level == "SHOW_BOTH"

    def test_ask_does_not_return_unauthorized_figures(self, svc):
        from api.authorization import Session
        session = Session(subject="fin", role_id=analyst_roles.FINANCIAL_ANALYST)
        r = svc.ask("What is occupancy?", session)
        assert r["status"] == "unauthorized"
        assert r["metric_ids"] == []
        assert r["headline_permitted"] is False
        # the engine's trust for occupancy is not rewritten
        assert svc.gate.authorize("M.OCC.001").effective_level == "SHOW_BOTH"

    def test_conversation_isolation(self, svc):
        from api.authorization import Session
        a = svc.ask("How much revenue did we make?",
                    Session(subject="alice", role_id=ROLE_OWNER))
        cid = a["conversation_id"]
        hidden = svc.conversation(cid, identity_subject="bob")
        assert hidden["found"] is False
        shown = svc.conversation(cid, identity_subject="alice")
        assert shown["found"] is True

    def test_conflict_endpoint_is_role_filtered(self, svc):
        occ = svc.conflict_view("M.OCC.001", analyst_roles.FINANCIAL_ANALYST)
        assert occ["available"] is False
        assert svc.gate.authorize("M.OCC.001").effective_level == "SHOW_BOTH"

    def test_tenant_claim_does_not_widen_access(self, registry, tmpdb):
        from fastapi.testclient import TestClient
        from api.auth import mint_token
        app = create_app(AnalyticsService(registry=registry, db_path=tmpdb,
                                          authenticator=suite_authenticator()),
                         authenticator=suite_authenticator(),
                         rate_limiter=RateLimiter(disabled=True))
        token = mint_token(TEST_SECRET, "fin", analyst_roles.FINANCIAL_ANALYST,
                           tenant_id="other-org", property_id="other-property")
        c = TestClient(app)
        r = c.get("/api/metrics/M.OCC.001",
                  headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["available"] is False

    def test_workspace_is_not_cross_role(self, registry, tmpdb):
        from fastapi.testclient import TestClient
        app = create_app(AnalyticsService(registry=registry, db_path=tmpdb,
                                          authenticator=suite_authenticator()),
                         authenticator=suite_authenticator(),
                         rate_limiter=RateLimiter(disabled=True))
        c = TestClient(app)
        r = c.get(f"/api/roles/{analyst_roles.OPERATIONS_ANALYST}/workspace",
                  headers=bearer_headers(analyst_roles.FINANCIAL_ANALYST, "fin"))
        assert r.status_code == 404


class TestLiveDataQuarantine:
    def test_unconfigured_live_source_cannot_bind(self, registry):
        live = ds.LiveDataSource.from_env()
        report = ds.RevalidationHarness(registry).run(live)
        assert report.passed is False
        with pytest.raises(ds.QuarantineError):
            ds.bind_source(live, report)

    def test_row_count_anomaly_requires_owner_decision(self, registry):
        class Divergent:
            def available(self):
                return True
            def fetch_table(self, logical_name, limit=None):
                return [{"id": 1}]
            def row_count(self, logical_name):
                return 1
            def columns(self, logical_name):
                return ("id",)
        live = ds.LiveDataSource(name="probe", connection=Divergent(), as_of="2026-08-29")
        report = ds.RevalidationHarness(registry).run(live)
        assert report.passed is False
        assert report.required_owner_decisions
        with pytest.raises(ds.QuarantineError):
            ds.bind_source(live, report)

    def test_write_sql_is_refused(self):
        assert _WRITE_SQL.search("INSERT INTO journal_entries VALUES (1)")
        pg = PostgresReadOnlyTransport(dsn="postgresql://unused")
        with pytest.raises(ds.DataSourceError):
            pg._execute("DELETE FROM journal_entries")

    def test_export_still_serves(self, svc):
        h = svc.health()
        assert h["data_source"]["kind"] == "export"
        assert h["data_source"]["status"] == ds.STATUS_TRUSTED
        assert h["live_data"]["status"] in (ds.STATUS_UNAVAILABLE, ds.STATUS_QUARANTINED,
                                            ds.STATUS_FAILED)
        assert h["live_data"]["remaining_requirement"]

    def test_relation_mapping_uses_manifest_logical_names(self):
        assert relation_from_logical("public.journal_entries") == ("public", "journal_entries")

    def test_source_interface_still_has_no_write_method(self):
        assert not hasattr(ds.LiveDataSource, "write")
        assert not hasattr(ds.LiveDataSource, "insert")
        assert not hasattr(ds.LiveDataSource, "execute_write")


class TestLlmEnableGate:
    def test_http_without_explicit_enable_refuses(self):
        from engine.llm_provider import LLMUnavailable
        with pytest.raises(LLMUnavailable):
            pc.build_provider(pc.ProviderConfig(mode=pc.MODE_HTTP, adapter_name="groq"))

    def test_enable_without_credentials_refuses(self, monkeypatch):
        from engine.llm_provider import LLMUnavailable
        monkeypatch.setenv(pc.ENV_ENABLE, "true")
        monkeypatch.setenv(pc.ENV_MODE, pc.MODE_HTTP)
        monkeypatch.setenv(pc.ENV_ADAPTER, "groq")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_BASE_URL", raising=False)
        cfg = pc.config_from_env()
        with pytest.raises(LLMUnavailable):
            pc.build_provider(cfg)

    def test_a_key_alone_does_not_enable(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk-not-a-real-key")
        monkeypatch.delenv(pc.ENV_ENABLE, raising=False)
        cfg = pc.config_from_env()
        assert cfg.explicitly_enabled is False
        assert cfg.mode == pc.MODE_OFFLINE
        for a in pc.available_adapters():
            if a["name"] == "groq":
                assert a["enabled"] is False

    def test_health_reports_llm_quarantine(self, svc):
        d = svc.health()["llm"]
        assert d["explicitly_enabled"] is False
        assert d["status"] == "QUARANTINED"
        assert d["remaining_requirement"]


class TestSecurityAndObservability:
    def test_api_responses_carry_security_headers(self, client):
        r = client.get("/api/trust")
        assert r.status_code == 200
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("X-Request-ID")
        assert "no-store" in (r.headers.get("Cache-Control") or "")

    def test_request_id_echo(self, client):
        r = client.get("/api/trust", headers={**bearer_headers(), "X-Request-ID": "rid-phase11"})
        assert r.headers.get("X-Request-ID") == "rid-phase11"

    def test_rate_limit_hook(self, registry, tmpdb):
        from fastapi.testclient import TestClient
        limiter = RateLimiter(limit=2, window=60)
        app = create_app(AnalyticsService(registry=registry, db_path=tmpdb,
                                          authenticator=suite_authenticator()),
                         authenticator=suite_authenticator(), rate_limiter=limiter)
        c = TestClient(app)
        c.headers.update(bearer_headers())
        assert c.get("/api/trust").status_code == 200
        assert c.get("/api/trust").status_code == 200
        assert c.get("/api/trust").status_code == 429

    def test_errors_are_sanitized(self):
        msg = sanitize_error(FileNotFoundError(r"D:\secret\evidence\foo.csv"))
        assert "evidence" not in msg.lower()
        assert "foo.csv" not in msg

    def test_secret_scan(self):
        assert contains_secret_material("Authorization: Bearer abc.def")
        assert contains_secret_material("postgresql://user:pass@host/db")
        assert not contains_secret_material("Revenue is reliable.")

    def test_oversized_question_is_rejected(self, client):
        r = client.post("/api/ask", json={"question": "x" * 5000})
        assert r.status_code == 422

    def test_health_exposes_counters(self, svc):
        h = svc.health()
        assert "observability" in h
        assert "counters" in h["observability"]


class TestFrontendDoesNotSendXRole:
    def test_api_js_does_not_send_x_role(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "api.js")
        src = open(path, encoding="utf-8").read()
        assert "x-role" not in src
        assert "Authorization" in src


class TestPhase11Validator:
    def test_the_phase11_validator_passes(self):
        import subprocess, sys
        r = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                          "scripts", "validate_phase11_consistency.py")],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        assert r.returncode == 0, (r.stdout or "")[-4000:] + (r.stderr or "")[-2000:]
        assert "No inconsistency" in r.stdout
