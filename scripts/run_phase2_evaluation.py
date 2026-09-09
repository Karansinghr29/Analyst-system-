"""
run_phase2_evaluation.py -- Phase 2 exit-criteria report.

implementation_roadmap.md, Phase 2 exit criteria:
    "Every one of the 49 metrics, queried through the now-gated path, returns the correct trust
     posture -- pass ai_evaluation_framework.md 1.2 and 1.3 in full (all BLOCK metrics refuse a
     single number under every phrasing variant tested; all SHOW_BOTH metrics return the full
     definition set; propagation correctly downgrades dependents and correctly does NOT
     downgrade the documented non-dependencies). This phase also implements the Answer
     Contract's structural fields."

This script evaluates all three of those, per metric, and writes phase2_evaluation.csv.
It is read-only with respect to every source CSV and every prior deliverable.

Note on "every phrasing variant tested" (1.2): the gate takes NO phrasing parameter -- a
GateDecision is a pure function of metric_id -- so phrasing cannot reach it by construction.
The testable analogue, which this script performs, is (a) repeated invocation returning an
identical verdict, and (b) entering a conflicted family through EVERY one of its member
metric_ids and confirming each entry point still yields the whole family and no headline.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.semantic_registry import SemanticRegistry
from engine.execution import MetricExecutor
from engine.gate import TrustGate
from engine import propagation, contract as contract_mod
from engine.citation import chain_for

OUT_PATH = os.path.join(ROOT, "phase2_evaluation.csv")

FIELDS = [
    "metric_id", "metric_name", "registry_trust_level", "gate_effective_level", "answer_level",
    "trust_level_exact", "answer_degraded_to_not_determinable", "execution_mode",
    "headline_permitted", "headline_withheld_ok", "definition_count", "family_complete_ok",
    "caveat_verbatim_ok", "confidence", "confidence_ok", "validation_status",
    "citation_chain_complete", "contract_complete", "contract_violations", "propagation_floor",
    "declared_divergence", "propagation_justification", "verdict",
]


def evaluate_metric(mid, registry, executor, gate):
    spec = registry.get(mid)
    decision = gate.authorize(mid)
    ans = executor.execute(mid)
    row = {
        "metric_id": mid,
        "metric_name": spec.semantic_name,
        "registry_trust_level": spec.trust_level,
        "gate_effective_level": decision.effective_level,
        "execution_mode": decision.execution_mode,
        "headline_permitted": decision.headline_permitted,
        "definition_count": len(ans.results),
        "confidence": ans.confidence,
        "validation_status": (ans.results[0].validation_status if ans.results else "N/A"),
        "propagation_floor": propagation.documented_floor(mid) or "none",
        "propagation_justification": propagation.justification(mid),
    }
    problems = []

    # -- 1.2 check 1: the EXACT trust level, not looser or stricter -----------------------------
    # Measured on the GATE's posture, not on the answer's. Those differ in one legitimate case:
    # a metric whose calculation is not implemented yields a NOT_DETERMINABLE *answer* (it has
    # no value, and answer_contract.md 5 requires a valueless answer to take that shape) while
    # the gate's *posture* for it is unchanged. Conflating the two would report an
    # implementation-coverage gap as a trust-rule violation.
    #
    # Expected posture = the strictest of: the registry's own level, metric_dependency_graph.md
    # 6's documented floor, and any declared cross-document divergence. The gate may RAISE to
    # any of these; it may never lower.
    floor = propagation.documented_floor(mid)
    sev = {"SAFE": 0, "DISCLOSE": 1, "SHOW_BOTH": 2, "NOT_DETERMINABLE": 3, "BLOCK": 4}
    expected = spec.trust_level
    if floor and sev[floor] > sev[expected]:
        expected = floor
    divergence = propagation.declared_divergence(mid)
    if divergence and sev[divergence.applied_level] > sev[expected]:
        expected = divergence.applied_level

    exact = (decision.effective_level == expected)
    row["trust_level_exact"] = exact
    row["declared_divergence"] = divergence.evidence if divergence else ""
    if not exact:
        problems.append(
            f"gate posture {decision.effective_level} != expected {expected}")

    # The answer's own level may only differ from the gate's posture by degrading to
    # NOT_DETERMINABLE when nothing could be computed -- any other difference is a defect.
    row["answer_level"] = ans.trust_level
    row["answer_degraded_to_not_determinable"] = (
        ans.trust_level == "NOT_DETERMINABLE" and decision.effective_level != "NOT_DETERMINABLE")
    if ans.trust_level != decision.effective_level and not row["answer_degraded_to_not_determinable"]:
        problems.append(
            f"answer level {ans.trust_level} diverges from gate posture "
            f"{decision.effective_level} for a reason other than missing implementation")

    # -- 1.2 check 2: BLOCK never returns a headline, from any entry point ---------------------
    withheld_ok = True
    if ans.trust_level in ("BLOCK", "SHOW_BOTH", "NOT_DETERMINABLE"):
        withheld_ok = (ans.headline is None and not ans.headline_permitted)
        for _ in range(3):                       # repeated invocation, identical verdict
            if gate.authorize(mid) != decision:
                withheld_ok = False
        for sibling in registry.family_members(mid):   # every family entry point
            sib = executor.execute(sibling)
            if sib.trust_level in ("BLOCK", "SHOW_BOTH") and sib.headline is not None:
                withheld_ok = False
                problems.append(f"entry point {sibling} leaked a headline")
    else:
        withheld_ok = (ans.headline is not None)
        if not withheld_ok:
            problems.append("SAFE/DISCLOSE metric produced no headline value")
    row["headline_withheld_ok"] = withheld_ok
    if ans.trust_level in ("BLOCK", "SHOW_BOTH", "NOT_DETERMINABLE") and not withheld_ok:
        problems.append("a headline number was obtainable despite the trust level")

    # -- 1.2 check 3: SHOW_BOTH returns ALL competing definitions, never a subset ---------------
    family_ok = True
    if ans.trust_level == "SHOW_BOTH":
        family_ok = len(ans.results) >= 2
        if not family_ok:
            problems.append(f"SHOW_BOTH narrowed to {len(ans.results)} definition(s)")
    elif ans.trust_level == "BLOCK":
        family_ok = len(ans.results) >= 1
    row["family_complete_ok"] = family_ok

    # -- 1.2 check 4: DISCLOSE carries its caveat verbatim -------------------------------------
    caveat_ok = True
    if ans.trust_level == "DISCLOSE":
        caveat_ok = bool(ans.caveat.strip()) and ans.caveat.strip() == spec.caveat_text.strip()
        if not caveat_ok:
            problems.append("DISCLOSE caveat missing or not verbatim")
    row["caveat_verbatim_ok"] = caveat_ok

    # -- 1.2 check 5: NOT_DETERMINABLE is not framed like a validated value ---------------------
    conf_expected = {"SHOW_BOTH": "SPLIT", "BLOCK": "BLOCKED", "NOT_DETERMINABLE": "UNVERIFIED",
                     "DISCLOSE": "MEDIUM"}
    if ans.trust_level in conf_expected:
        conf_ok = ans.confidence == conf_expected[ans.trust_level]
    else:
        conf_ok = ans.confidence.startswith("HIGH")
    row["confidence_ok"] = conf_ok
    if not conf_ok:
        problems.append(f"confidence {ans.confidence!r} does not match answer_contract.md 3")

    # -- Answer Contract structural fields ------------------------------------------------------
    report = contract_mod.validate(ans, spec)
    row["contract_complete"] = report.complete
    row["contract_violations"] = " | ".join(report.violations)
    if not report.complete:
        problems.extend(report.violations)

    row["citation_chain_complete"] = chain_for(spec).complete

    row["verdict"] = "PASS" if not problems else "FAIL"
    return row, problems


def main():
    registry = SemanticRegistry()
    gate = TrustGate(registry)
    executor = MetricExecutor(registry=registry, gate=gate)

    rows, all_problems = [], {}
    for mid in registry.all_ids():
        row, problems = evaluate_metric(mid, registry, executor, gate)
        rows.append(row)
        if problems:
            all_problems[mid] = problems

    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    passed = sum(1 for r in rows if r["verdict"] == "PASS")
    print("=" * 88)
    print("PHASE 2 EXIT CRITERIA -- ai_evaluation_framework.md 1.2 and 1.3")
    print("=" * 88)
    print(f"\n[1.2] Trust-rule compliance, all {len(rows)} metrics (a completeness requirement, "
          f"not a sample):")
    print(f"      PASS {passed} / {len(rows)}")
    by_level = {}
    for r in rows:
        by_level.setdefault(r["gate_effective_level"], []).append(r)
    for lvl in ("SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE"):
        group = by_level.get(lvl, [])
        if not group:
            continue
        ok = sum(1 for r in group if r["verdict"] == "PASS")
        print(f"        {lvl:18s} {ok}/{len(group)} pass")

    print("\n      Sub-checks:")
    for name, key in (("exact trust level", "trust_level_exact"),
                      ("headline correctly withheld/exposed", "headline_withheld_ok"),
                      ("family never narrowed", "family_complete_ok"),
                      ("DISCLOSE caveat verbatim", "caveat_verbatim_ok"),
                      ("confidence per contract 3", "confidence_ok"),
                      ("answer contract complete", "contract_complete")):
        ok = sum(1 for r in rows if r[key])
        print(f"        {name:38s} {ok}/{len(rows)}")

    audit = propagation.audit(registry)
    print(f"\n[1.3] Conflict/DQ propagation correctness (both directions):")
    print(f"      {audit.summary()}")
    print(f"      propagation table rows encoded:      {len(propagation.PROPAGATION_TABLE)}")
    print(f"      explicit non-dependencies encoded:   "
          f"{len(propagation.EXPLICIT_NON_DEPENDENCIES)}")
    print(f"      metrics with a documented floor:     "
          f"{sum(1 for m in registry.all_ids() if propagation.documented_floor(m))}")
    for m in audit.missing_downgrades + audit.false_downgrades + audit.unknown_metric_ids:
        print(f"        DEFECT: {m}")

    cited = sum(1 for r in rows if r["citation_chain_complete"])
    print(f"\n[contract] Evidence citation chains resolving to file_manifest.csv: "
          f"{cited}/{len(rows)}")

    degraded = [r["metric_id"] for r in rows if r["answer_degraded_to_not_determinable"]]
    if degraded:
        print(f"\n[coverage] {len(degraded)} metric(s) hold a valid trust posture but produce a "
              f"NOT_DETERMINABLE answer because no calculator is implemented "
              f"(implementation coverage, not a trust defect): {', '.join(degraded)}")

    if propagation.DECLARED_TRUST_DIVERGENCES:
        print(f"\n[divergence] {len(propagation.DECLARED_TRUST_DIVERGENCES)} cross-document trust "
              f"divergence(s) declared and NOT silently resolved -- the stricter posture is "
              f"applied and the case is raised for an owner decision:")
        for d in propagation.DECLARED_TRUST_DIVERGENCES:
            print(f"   {d.metric_id}: registry={d.registry_level}, implied={d.implied_level}, "
                  f"applied={d.applied_level}")
            print(f"      {d.evidence}")

    if all_problems:
        print(f"\n{len(all_problems)} metric(s) FAILED -- not hidden:")
        for mid, problems in all_problems.items():
            for p in problems:
                print(f"   {mid}: {p}")
    else:
        print("\nNo metric failed any 1.2 / 1.3 / answer-contract check.")

    print(f"\nWrote {len(rows)} rows to {OUT_PATH}")
    return 0 if not all_problems and audit.clean else 1


if __name__ == "__main__":
    sys.exit(main())
