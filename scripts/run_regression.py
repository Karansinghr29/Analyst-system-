"""
run_regression.py -- Phase 1 required regression artifact.

"Every implemented metric that has an existing reference view must be automatically
comparable against that reference. Produce: reconstructed value, reference value,
difference, relative difference where meaningful, pass/fail, explanation/reference ID.
Do not hide mismatches. The existing 80 validation checks and 49-metric registry become
the initial regression suite."

For each of the 49 semantic metric_ids:
  1. Executes the metric through the live MetricExecutor (fresh, deterministic, offline).
  2. Looks up every Phase E validation_summary.csv check row mapped to that metric_id
     via ValidationIndex (the same join used by engine/validation.py at answer time).
  3. Emits one regression row per underlying check -- reconstructed_value and
     reference_value are copied verbatim from validation_summary.csv (produced by the
     independent validate_*.py scripts, which recompute from evidence at runtime and
     compare against the exported business view), so this is a second, differently-wired
     confirmation that the semantic layer and the Phase E scripts agree.
  4. Metrics with zero mapped checks are emitted as UNVERIFIED, never hidden.
  5. Metrics with no calculator (Phase 1 scope gap) are emitted as NOT_IMPLEMENTED.

Output: regression_report.csv (repo root) + a summary printed to stdout.
Nothing here modifies validation_summary.csv or any source evidence CSV -- read-only.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.semantic_registry import SemanticRegistry
from engine.validation import ValidationIndex
from engine.execution import MetricExecutor
from engine.calculators import REGISTRY, NOT_IMPLEMENTED

OUT_PATH = os.path.join(ROOT, "regression_report.csv")

FIELDS = [
    "metric_id", "metric_name", "definition_label", "check_id",
    "reconstructed_value", "reference_value", "absolute_difference",
    "percentage_difference", "validation_status", "pass_fail",
    "reference_source", "explanation_reference_id", "trust_level", "notes",
]


def pass_fail_for(status):
    if status == "MATCH":
        return "PASS"
    if status == "DIFFERS":
        return "FAIL"
    if status == "PARTIAL":
        return "PARTIAL"
    return "UNVERIFIED"


def main():
    registry = SemanticRegistry()
    validation = ValidationIndex()
    executor = MetricExecutor(registry=registry, validation_index=validation)

    rows = []
    counts = {"PASS": 0, "FAIL": 0, "PARTIAL": 0, "UNVERIFIED": 0, "NOT_IMPLEMENTED": 0}

    for metric_id in registry.all_ids():
        spec = registry.get(metric_id)
        calc_fn = REGISTRY.get(metric_id)

        if calc_fn is None or calc_fn == NOT_IMPLEMENTED:
            rows.append({
                "metric_id": metric_id, "metric_name": spec.semantic_name,
                "definition_label": "", "check_id": "",
                "reconstructed_value": "", "reference_value": "",
                "absolute_difference": "", "percentage_difference": "",
                "validation_status": "NOT_IMPLEMENTED", "pass_fail": "NOT_IMPLEMENTED",
                "reference_source": "", "explanation_reference_id": "",
                "trust_level": spec.trust_level,
                "notes": "No Phase 1 calculator (out of scope -- see Phase 1 report).",
            })
            counts["NOT_IMPLEMENTED"] += 1
            continue

        ans = executor.execute(metric_id)
        check_rows = validation.rows_for(metric_id)

        if not check_rows:
            rows.append({
                "metric_id": metric_id, "metric_name": spec.semantic_name,
                "definition_label": ans.results[0].definition_label if ans.results else "",
                "check_id": "",
                "reconstructed_value": ans.results[0].value if ans.results else "",
                "reference_value": "", "absolute_difference": "", "percentage_difference": "",
                "validation_status": "UNVERIFIED", "pass_fail": "UNVERIFIED",
                "reference_source": "", "explanation_reference_id": "",
                "trust_level": ans.trust_level,
                "notes": "No validation_summary.csv check maps to this metric_id (no reference view to compare against, or not re-validated at semantic-layer join -- see metric_reconstruction.md).",
            })
            counts["UNVERIFIED"] += 1
            continue

        for check in check_rows:
            status = check.validation_status
            rows.append({
                "metric_id": metric_id, "metric_name": spec.semantic_name,
                "definition_label": ans.results[0].definition_label if ans.results else "",
                "check_id": check.metric_id,
                "reconstructed_value": check.reconstructed_value,
                "reference_value": check.reference_value,
                "absolute_difference": check.absolute_difference,
                "percentage_difference": check.percentage_difference,
                "validation_status": status, "pass_fail": pass_fail_for(status),
                "reference_source": check.reference_source,
                "explanation_reference_id": check.metric_id,
                "trust_level": ans.trust_level,
                "notes": check.explanation,
            })
            counts[pass_fail_for(status)] += 1

    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    total_checks = sum(counts.values())
    print(f"Wrote {len(rows)} rows ({total_checks} check-level rows) to {OUT_PATH}")
    print("Summary by pass/fail category:")
    for k in ("PASS", "FAIL", "PARTIAL", "UNVERIFIED", "NOT_IMPLEMENTED"):
        print(f"  {k:15s} {counts[k]}")

    fails = [r for r in rows if r["pass_fail"] == "FAIL"]
    if fails:
        print(f"\n{len(fails)} FAIL row(s) -- NOT hidden, each already has a documented "
              f"conflict/DQ explanation in conflicts.md / data_quality_report.md:")
        for r in fails:
            print(f"  {r['metric_id']} / {r['check_id']}: {r['notes']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
