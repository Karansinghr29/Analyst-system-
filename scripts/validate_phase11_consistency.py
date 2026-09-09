"""
validate_phase11_consistency.py -- Phase 11 anti-drift validator.

  1. source CSVs byte-identical
  2. default service still serves the TRUSTED export
  3. live source is QUARANTINED / UNAVAILABLE until enable+harness pass
  4. LLM default is offline; HTTP without enable refuses
  5. unauthenticated /api/ is 401; x-role is not identity
  6. authorization never changes a trust level
  7. no write method on DataSource
  8. security headers present
  9. frontend api.js does not send x-role
 10. Phase 11 artifacts exist
 11. no adapter enabled merely because a credential is present
"""
import csv
import hashlib
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine import analyst_roles

from api.service import AnalyticsService, create_app
from api.authorization import ROLE_OWNER
from api import data_source as ds
from api import provider_config as pc
from api.auth import suite_authenticator, bearer_headers, FailClosedAuthenticator
from api.security import RateLimiter

BASELINE_SHA = "aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26"
ARTIFACTS = (
    "phase11_production_readiness_plan.md", "phase11_security_spec.md",
    "phase11_data_activation_spec.md", "phase11_llm_activation_spec.md",
    "phase11_auth_spec.md", "phase11_observability_spec.md",
    "phase11_production_readiness_report.md",
)


def main():
    problems, warnings = [], []
    registry = SemanticRegistry()
    gate = TrustGate(registry)
    tmp = tempfile.mkdtemp()
    svc = AnalyticsService(registry=registry, db_path=os.path.join(tmp, "v11.db"),
                           authenticator=suite_authenticator())

    # 1 integrity
    with open(os.path.join(ROOT, "evidence", "file_manifest.csv"), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    h = hashlib.sha256()
    for r in rows:
        p = os.path.join(ROOT, r["file"])
        if not os.path.exists(p):
            problems.append(f"[1] missing source CSV {r['file']}")
            continue
        with open(p, "rb") as fh:
            h.update(fh.read())
    digest = h.hexdigest()
    if digest != BASELINE_SHA:
        problems.append(f"[1] SOURCE CSVs CHANGED: {digest} != {BASELINE_SHA}")

    # 2 export still serving
    health = svc.health()
    if health["data_source"]["kind"] != "export" or health["data_source"]["status"] != ds.STATUS_TRUSTED:
        problems.append("[2] default service is not serving the trusted export")
    if not health["revalidation"]["passed"]:
        problems.append("[2] export revalidation did not pass")

    # 3 live quarantined
    live = health["live_data"]
    if live.get("revalidation", {}).get("passed"):
        warnings.append("[3] live revalidation reported a pass — confirm this was a real harness run")
    else:
        if not live.get("remaining_requirement"):
            problems.append("[3] quarantined live source did not name a remaining requirement")

    # 4 LLM
    if health["llm"].get("explicitly_enabled"):
        warnings.append("[4] LLM is explicitly enabled in this environment")
    else:
        if health["llm"].get("network_access"):
            problems.append("[4] LLM reports network access without explicit enable")
    try:
        pc.build_provider(pc.ProviderConfig(mode=pc.MODE_HTTP, adapter_name="groq"))
        problems.append("[4] HTTP adapter constructed without explicit enable")
    except Exception:
        pass
    for a in pc.available_adapters():
        if a["enabled"] and not (os.environ.get(pc.ENV_ENABLE) or "").lower() == "true":
            problems.append(f"[4] adapter {a['name']} enabled without AI_ANALYTICS_LLM_ENABLE=true")

    # 5 auth
    from fastapi.testclient import TestClient
    app = create_app(svc, authenticator=suite_authenticator(),
                     rate_limiter=RateLimiter(disabled=True))
    bare = TestClient(app)
    r = bare.get("/api/owner/home")
    if r.status_code != 401:
        problems.append(f"[5] unauthenticated /api/owner/home returned {r.status_code}, not 401")
    r = bare.get("/api/owner/home", headers={"x-role": "owner"})
    if r.status_code != 401:
        problems.append("[5] x-role was accepted as identity")
    authed = TestClient(app)
    authed.headers.update(bearer_headers())
    r = authed.get("/api/owner/home")
    if r.status_code != 200:
        problems.append(f"[5] authenticated owner home failed ({r.status_code})")
    if bare.get("/health").status_code != 200:
        problems.append("[5] /health is no longer public")

    # 6 trust invariant
    fin = analyst_roles.FINANCIAL_ANALYST
    home = svc.owner_home(fin)
    for t in home["business_health"] + home["operations"] + home["risks"]:
        expected = gate.authorize(t["metric_id"]).effective_level
        if t["trust"]["trust_level"] != expected:
            problems.append(f"[6] {t['metric_id']} trust changed for {fin}")

    # 7 no write
    for name in ("write", "insert", "update", "delete", "execute_write"):
        if hasattr(ds.DataSource, name) or hasattr(ds.LiveDataSource, name):
            problems.append(f"[7] DataSource exposes {name}")

    # 8 headers
    r = authed.get("/api/trust")
    if r.headers.get("X-Content-Type-Options") != "nosniff":
        problems.append("[8] missing nosniff header")
    if not r.headers.get("X-Request-ID"):
        problems.append("[8] missing X-Request-ID")

    # 9 frontend
    api_js = open(os.path.join(ROOT, "frontend", "api.js"), encoding="utf-8").read()
    if "x-role" in api_js:
        problems.append("[9] frontend/api.js still sends x-role")
    if "Authorization" not in api_js:
        problems.append("[9] frontend/api.js has no Authorization header")

    # 10 artifacts
    for a in ARTIFACTS:
        if not os.path.exists(os.path.join(ROOT, a)):
            problems.append(f"[10] missing {a}")

    # 11 fail-closed default
    if FailClosedAuthenticator().describe()["status"] != "QUARANTINED":
        problems.append("[11] fail-closed authenticator is not reported as QUARANTINED")

    print("=" * 88)
    print("PHASE 11 CONSISTENCY VALIDATION -- production activation vs. the live engine")
    print("=" * 88)
    print(f"\n[export]        {health['data_source']['status']}")
    print(f"[live]          {live['status']} -- {live.get('remaining_requirement', '')[:80]}")
    print(f"[llm]           {health['llm']['status']}")
    print(f"[auth]          {health['auth']['status']}")
    print(f"[source]        SHA-256 {digest[:16]}... "
          f"{'MATCHES baseline' if digest == BASELINE_SHA else 'CHANGED'}")
    print(f"\n[problems]      {len(problems)}")
    print(f"[warnings]      {len(warnings)}")
    if problems:
        print("\nINCONSISTENCIES:")
        for p in problems:
            print(f"   {p}")
    else:
        print("\nNo inconsistency between Phase 11 activation and the engine.")
    for w in warnings:
        print(f"   warning: {w}")
    svc.close()
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
