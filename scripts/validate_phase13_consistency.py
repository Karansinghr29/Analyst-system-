"""
validate_phase13_consistency.py -- Phase 13 anti-drift validator.

  1. source CSVs byte-identical
  2. metric / conflict / DQ registries byte-identical
  3. default service still serves the TRUSTED export
  4. live is QUARANTINED / UNAVAILABLE until enable+freeze+harness pass
  5. REST remains GET-only; no native SQL API
  6. Trust Gate / Answer Contract / calculators do not import Supabase
  7. Phase 12 artifacts still exist
  8. Phase 13 artifacts exist
  9. owner-decision loader is read-only
 10. pagination helpers exist
"""
import csv
import hashlib
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.gate import TrustGate
from engine.semantic_registry import SemanticRegistry
from api.service import AnalyticsService
from api import data_source as ds
from api.auth import suite_authenticator
from api.live_connector import parse_content_range, PAGE_SIZE
from api.owner_decisions import load_owner_decisions

BASELINE_SHA = "aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26"
REGISTRY_SHA = {
    "semantic_metric_registry.csv":
        "de9e8acf87c4bb200fb25d7cc9b73a7bc1576bbff97941a5725da94292e4c393",
    "conflict_disclosure_registry.csv":
        "12f636c1d22728b7e34c2bde23ce77c0d73c775f5914d4a346824f055d8885b4",
    "data_quality_registry.csv":
        "caed9805b97d767ef9d2e82557bdf266ed7629fed8e84668e266feff690b3690",
}
ARTIFACTS = (
    "phase13_live_data_spec.md", "phase13_implementation_plan.md", "phase13_report.md",
)
PHASE12 = (
    "phase12_local_llm_spec.md", "phase12_implementation_plan.md", "phase12_report.md",
)
UNTOUCHED = (
    "engine/gate.py", "engine/trust_gate.py", "engine/propagation.py",
    "engine/contract.py", "engine/answer_renderer.py", "engine/structured_output.py",
)


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    problems, warnings = [], []
    registry = SemanticRegistry()
    gate = TrustGate(registry)
    tmp = tempfile.mkdtemp()
    svc = AnalyticsService(registry=registry, db_path=os.path.join(tmp, "v13.db"),
                           authenticator=suite_authenticator())

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

    for name, expected in REGISTRY_SHA.items():
        actual = _sha_file(os.path.join(ROOT, name))
        if actual != expected:
            problems.append(f"[2] {name} changed ({actual} != {expected})")

    health = svc.health()
    if health["data_source"]["kind"] != "export" or health["data_source"]["status"] != ds.STATUS_TRUSTED:
        problems.append("[3] default service is not serving the trusted export")
    live = health["live_data"]
    if live.get("revalidation", {}).get("passed"):
        warnings.append("[4] live revalidation reported a pass — confirm a real harness run")
    elif not live.get("remaining_requirement"):
        problems.append("[4] quarantined live source did not name a remaining requirement")

    conn_src = open(os.path.join(ROOT, "api", "live_connector.py"), encoding="utf-8").read()
    if 'method="POST"' in conn_src or "method='POST'" in conn_src:
        problems.append("[5] live connector gained a POST")
    if "parse_content_range" not in conn_src or PAGE_SIZE < 1:
        problems.append("[5] pagination helpers missing")
    try:
        parse_content_range("0-9/10")
    except Exception as e:
        problems.append(f"[5] parse_content_range failed: {type(e).__name__}")
    if "select=" in open(os.path.join(ROOT, "api", "service.py"), encoding="utf-8").read() and \
            "/sql" in open(os.path.join(ROOT, "api", "service.py"), encoding="utf-8").read():
        problems.append("[5] service exposed a SQL endpoint")

    for rel in UNTOUCHED:
        src = open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8").read()
        if "SUPABASE_" in src or "PostgREST" in src:
            problems.append(f"[6] {rel} must not import the live connector")

    if gate.authorize("M.PROFIT.001").effective_level != "BLOCK":
        problems.append("[6] Trust Gate is no longer authoritative for M.PROFIT.001")
    if gate.authorize("M.OCC.001").effective_level != "SHOW_BOTH":
        problems.append("[6] Trust Gate is no longer authoritative for M.OCC.001")

    for a in PHASE12:
        if not os.path.exists(os.path.join(ROOT, a)):
            problems.append(f"[7] missing Phase 12 artifact {a}")
    for a in ARTIFACTS:
        if not os.path.exists(os.path.join(ROOT, a)):
            problems.append(f"[8] missing {a}")

    od = open(os.path.join(ROOT, "api", "owner_decisions.py"), encoding="utf-8").read()
    if "json.dump" in od or "\"w\"" in od:
        problems.append("[9] owner_decisions.py looks writable")
    if load_owner_decisions() != ():
        warnings.append("[9] owner-decision file is non-empty")

    ask = open(os.path.join(ROOT, "frontend", "views", "chat.js"), encoding="utf-8").read()
    if "/api/ask" not in ask:
        problems.append("[10] frontend chat no longer posts /api/ask")

    print("=" * 88)
    print("PHASE 13 CONSISTENCY VALIDATION -- live freeze vs. the trusted export")
    print("=" * 88)
    print(f"\n[export]        {health['data_source']['status']}")
    print(f"[live]          {live['status']}")
    print(f"[source]        SHA-256 {digest[:16]}... "
          f"{'MATCHES baseline' if digest == BASELINE_SHA else 'CHANGED'}")
    print(f"\n[problems]      {len(problems)}")
    print(f"[warnings]      {len(warnings)}")
    if problems:
        print("\nINCONSISTENCIES:")
        for p in problems:
            print(f"   {p}")
    else:
        print("\nNo inconsistency between Phase 13 live freeze rules and the engine.")
    for w in warnings:
        print(f"   warning: {w}")
    svc.close()
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
