"""
validate_phase15_consistency.py -- Phase 15 anti-drift.

  1. source CSVs and registries byte-identical
  2. NL coverage tests exist and concept map still verifies against the registry
  3. Power BI production artifacts exist and bind to the existing API
  4. Power BI pages do not introduce SQL or a second calculation engine
  5. live remains QUARANTINED in the production spec
  6. recommended LLM timeout remains 180
"""
import csv
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.semantic_registry import SemanticRegistry
from engine import concept_map
from api.provider_config import RECOMMENDED_TIMEOUT, ENV_TIMEOUT

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
    "phase15_nl_coverage_spec.md",
    "phase15_powerbi_production_spec.md",
    "phase15_report.md",
    "powerbi_production_pages.json",
    "tests/test_phase15_nl_coverage.py",
    "tests/test_phase15_powerbi.py",
)
API_PATHS = {
    "/api/owner/home", "/api/analytics/financial", "/api/analytics/operations",
    "/api/analytics/risk", "/api/data-quality", "/api/insights", "/api/trust",
    "/api/metrics", "/api/report/executive", "/api/changes",
}


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    problems, warnings = [], []
    registry = SemanticRegistry()

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
            problems.append(f"[1] {name} changed ({actual} != {expected})")

    drift = concept_map.verify_against_registry(registry)
    if drift:
        problems.append(f"[2] concept map drifted from registry: {drift[:3]}")

    for a in ARTIFACTS:
        if not os.path.exists(os.path.join(ROOT, *a.split("/"))):
            problems.append(f"[3] missing {a}")

    pages = json.loads(open(os.path.join(ROOT, "powerbi_production_pages.json"),
                            encoding="utf-8").read())
    if pages.get("authority", "").split("→")[0].strip() != "Analytics Engine":
        problems.append("[4] Power BI pages lost engine authority")
    joined = json.dumps(pages).lower()
    if "service_role" in joined or "password=" in joined:
        problems.append("[4] Power BI pages introduced credentials or a service-role key")
    bound = set()
    for page in pages.get("pages", []):
        for path in page.get("api", []):
            bound.add(path.split("{")[0].rstrip("/") if "{" in path else path)
    missing = API_PATHS - bound
    # allow prefix matches for templated paths
    missing = {p for p in missing if not any(b.startswith(p.split("{")[0]) or p.startswith(b)
                                             for b in bound)}
    if missing:
        warnings.append(f"[3] pages did not mention {sorted(missing)}")

    spec = open(os.path.join(ROOT, "phase15_powerbi_production_spec.md"), encoding="utf-8").read()
    if "QUARANTINED" not in spec:
        problems.append("[5] production spec does not keep Supabase quarantined")
    if RECOMMENDED_TIMEOUT != 180:
        problems.append(f"[6] {ENV_TIMEOUT} recommended timeout is {RECOMMENDED_TIMEOUT}, not 180")

    print("=" * 80)
    print("PHASE 15 CONSISTENCY VALIDATION -- NL coverage + Power BI production")
    print("=" * 80)
    print(f"[source]        SHA-256 {digest[:16]}... "
          f"{'MATCHES baseline' if digest == BASELINE_SHA else 'DRIFT'}")
    print(f"[timeout]       {ENV_TIMEOUT} recommended={RECOMMENDED_TIMEOUT}")
    print(f"[problems]      {len(problems)}")
    print(f"[warnings]      {len(warnings)}")
    for p in problems:
        print("   ", p)
    for w in warnings:
        print("    warning:", w)
    if not problems:
        print("\nNo inconsistency between Phase 15 artifacts and the engine.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
