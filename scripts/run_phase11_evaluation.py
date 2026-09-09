"""
run_phase11_evaluation.py -- Phase 11 activation evaluation.

Offline. Never contacts a live database or a live model. Records whether each
production boundary is enforced or honestly quarantined.
"""
import csv
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.llm_provider import CallableProvider, DeterministicMockProvider
from engine import analyst_roles

from api.service import AnalyticsService, create_app
from api.authorization import ROLE_OWNER, Session
from api import data_source as ds
from api import provider_config as pc
from api.auth import (FailClosedAuthenticator, suite_authenticator, bearer_headers,
                      AuthenticationError)
from api.security import RateLimiter
from api.provider_config import ProviderConfig, MODE_CALLABLE

OUT_PATH = os.path.join(ROOT, "phase11_evaluation.csv")
FIELDS = ["scenario", "category", "expectation", "verdict", "reason"]


def _row(scenario, category, expectation, ok, reason=""):
    return {
        "scenario": scenario, "category": category, "expectation": expectation,
        "verdict": "PASS" if ok else "FAIL", "reason": reason,
    }


def main():
    registry = SemanticRegistry()
    gate = TrustGate(registry)
    tmp = tempfile.mkdtemp()
    svc = AnalyticsService(registry=registry, db_path=os.path.join(tmp, "eval.db"),
                           authenticator=suite_authenticator())
    app = create_app(svc, authenticator=suite_authenticator(),
                     rate_limiter=RateLimiter(disabled=True))
    client = TestClient(app)
    client.headers.update(bearer_headers())
    bare = TestClient(app)
    rows = []

    r = bare.get("/api/owner/home")
    rows.append(_row("unauthenticated /api/owner/home", "auth", "401",
                     r.status_code == 401, f"status={r.status_code}"))

    r = bare.get("/api/owner/home", headers={"x-role": "owner"})
    rows.append(_row("x-role is not identity", "auth", "401",
                     r.status_code == 401, f"status={r.status_code}"))

    r = client.get("/api/owner/home")
    rows.append(_row("HMAC bearer owner home", "auth", "200",
                     r.status_code == 200, f"status={r.status_code}"))

    try:
        FailClosedAuthenticator().authenticate({"Authorization": "Bearer x"})
        rows.append(_row("fail-closed authenticator", "auth", "raises", False, "did not raise"))
    except AuthenticationError:
        rows.append(_row("fail-closed authenticator", "auth", "raises", True))

    vis = set(svc.authorizer.filter_metrics(analyst_roles.FINANCIAL_ANALYST))
    occ_ok = "M.OCC.001" not in vis and svc.metric_detail(
        "M.OCC.001", analyst_roles.FINANCIAL_ANALYST)["available"] is False
    rows.append(_row("financial role cannot read occupancy figures", "authz",
                     "unavailable", occ_ok))

    trust_ok = True
    home = svc.owner_home(analyst_roles.FINANCIAL_ANALYST)
    for t in home["business_health"] + home["operations"] + home["risks"]:
        if t["trust"]["trust_level"] != gate.authorize(t["metric_id"]).effective_level:
            trust_ok = False
    rows.append(_row("authorization does not change trust", "authz",
                     "gate posture unchanged", trust_ok))

    a = svc.ask("How much revenue did we make?", Session(subject="alice", role_id=ROLE_OWNER))
    hidden = svc.conversation(a["conversation_id"], identity_subject="bob")["found"] is False
    rows.append(_row("conversation isolation by subject", "authz", "404/not found", hidden))

    live = ds.LiveDataSource.from_env()
    report = ds.RevalidationHarness(registry, gate, svc.executor).run(live)
    bind_refused = False
    try:
        ds.bind_source(live, report)
    except ds.QuarantineError:
        bind_refused = True
    rows.append(_row("unconfigured live source cannot bind", "live",
                     "quarantined", (not report.passed) and bind_refused,
                     report.remaining_requirement or report.notes))

    h = svc.health()
    rows.append(_row("export still serving", "live", "trusted export",
                     h["data_source"]["kind"] == "export"
                     and h["data_source"]["status"] == ds.STATUS_TRUSTED))
    rows.append(_row("live remaining requirement named", "live", "named",
                     bool(h["live_data"].get("remaining_requirement"))))

    try:
        pc.build_provider(pc.ProviderConfig(mode=pc.MODE_HTTP, adapter_name="groq"))
        llm_refused = False
    except Exception:
        llm_refused = True
    rows.append(_row("HTTP adapter without enable refuses", "llm", "LLMUnavailable",
                     llm_refused))
    rows.append(_row("LLM default quarantined", "llm", "QUARANTINED",
                     h["llm"]["status"] == "QUARANTINED" and not h["llm"]["network_access"]))

    def hostile(prompt, system, max_tokens, temperature):
        if "VERBALIZE" in system:
            return "Profit is Rs.5,000,000 (M.PROFIT.001)."
        return DeterministicMockProvider()._extract(prompt)

    hostile_svc = AnalyticsService(
        registry=registry, db_path=os.path.join(tmp, "adv.db"),
        authenticator=suite_authenticator(),
        provider_config=ProviderConfig(mode=MODE_CALLABLE, fn=hostile))
    adv = hostile_svc.ask("What's our profit?", Session(subject="owner", role_id=ROLE_OWNER))
    rows.append(_row("hostile verbalization still guarded", "adversarial",
                     "guard or fallback, no BLOCK headline",
                     adv["headline_permitted"] is False and (
                         adv.get("guard_violations") or adv.get("llm_fallback")),
                     f"trust={adv.get('trust_level')}"))
    hostile_svc.close()

    r = client.get("/api/trust")
    rows.append(_row("security headers present", "security",
                     "nosniff + request id",
                     r.headers.get("X-Content-Type-Options") == "nosniff"
                     and bool(r.headers.get("X-Request-ID"))))

    r = client.post("/api/ask", json={"question": "x" * 5000})
    rows.append(_row("oversized question rejected", "security", "422",
                     r.status_code == 422, f"status={r.status_code}"))

    limiter = RateLimiter(limit=2, window=60)
    limited = TestClient(create_app(
        AnalyticsService(registry=registry, db_path=os.path.join(tmp, "rl.db"),
                         authenticator=suite_authenticator()),
        authenticator=suite_authenticator(), rate_limiter=limiter))
    limited.headers.update(bearer_headers())
    limited.get("/api/trust")
    limited.get("/api/trust")
    r = limited.get("/api/trust")
    rows.append(_row("rate limit hook", "security", "429", r.status_code == 429,
                     f"status={r.status_code}"))

    api_js = open(os.path.join(ROOT, "frontend", "api.js"), encoding="utf-8").read()
    rows.append(_row("frontend does not send x-role", "frontend", "Authorization only",
                     "x-role" not in api_js and "Authorization" in api_js))

    svc.close()

    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    failed = [r for r in rows if r["verdict"] != "PASS"]
    print(f"phase11_evaluation.csv: {len(rows)} scenarios, {len(failed)} FAIL")
    for r in failed:
        print(f"  FAIL {r['scenario']}: {r['reason']}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
