"""
validate_phase16_consistency.py -- Phase 16 anti-drift.

  1. source CSVs and registries byte-identical
  2. Power BI is a first-class frontend route
  3. BI module uses existing APIs only (no fetch outside api.js)
  4. no fake embed / secrets
  5. Phase 15 Power BI artifacts still present
  6. calculators / gate / Ollama / live connector untouched by this validator's SHA checks
"""
import csv
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

BASELINE_SHA = "aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26"
REGISTRY_SHA = {
    "semantic_metric_registry.csv":
        "de9e8acf87c4bb200fb25d7cc9b73a7bc1576bbff97941a5725da94292e4c393",
    "conflict_disclosure_registry.csv":
        "12f636c1d22728b7e34c2bde23ce77c0d73c775f5914d4a346824f055d8885b4",
    "data_quality_registry.csv":
        "caed9805b97d767ef9d2e82557bdf266ed7629fed8e84668e266feff690b3690",
}
FRONTEND = os.path.join(ROOT, "frontend")
REQUIRED = (
    "frontend/app.js", "frontend/bi_nav.js", "frontend/views/powerbi.js",
    "powerbi_production_pages.json", "phase15_powerbi_production_spec.md",
    "tests/test_phase16_bi_module.py",
)


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    problems = []
    with open(os.path.join(ROOT, "evidence", "file_manifest.csv"), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    h = hashlib.sha256()
    for r in rows:
        p = os.path.join(ROOT, r["file"])
        if not os.path.exists(p):
            problems.append(f"[1] missing {r['file']}")
            continue
        with open(p, "rb") as fh:
            h.update(fh.read())
    digest = h.hexdigest()
    if digest != BASELINE_SHA:
        problems.append(f"[1] SOURCE CSVs CHANGED: {digest} != {BASELINE_SHA}")
    for name, expected in REGISTRY_SHA.items():
        actual = _sha_file(os.path.join(ROOT, name))
        if actual != expected:
            problems.append(f"[1] {name} changed")

    for rel in REQUIRED:
        if not os.path.exists(os.path.join(ROOT, *rel.split("/"))):
            problems.append(f"[2] missing {rel}")

    app = open(os.path.join(FRONTEND, "app.js"), encoding="utf-8").read()
    if "Power BI" not in app or "#/bi/executive" not in app:
        problems.append("[2] Power BI is not a first-class nav route")

    pbi = open(os.path.join(FRONTEND, "views", "powerbi.js"), encoding="utf-8").read()
    if "fetch(" in pbi:
        problems.append("[3] powerbi.js performs I/O")
    if "api.analyticsSection" not in pbi or "api.ownerHome" not in pbi:
        problems.append("[3] BI module does not consume the existing analytics API")
    if "<iframe" in pbi.lower() or "embedToken" in pbi:
        problems.append("[4] BI module contains a fake embed or token")
    if "powerbi-service-attach" not in pbi:
        problems.append("[4] Service attach boundary is missing")

    print("=" * 80)
    print("PHASE 16 CONSISTENCY VALIDATION -- Power BI product module")
    print("=" * 80)
    print(f"[source]        SHA-256 {digest[:16]}... "
          f"{'MATCHES baseline' if digest == BASELINE_SHA else 'DRIFT'}")
    print(f"[problems]      {len(problems)}")
    for p in problems:
        print("   ", p)
    if not problems:
        print("\nNo inconsistency between Phase 16 BI module and the engine.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
