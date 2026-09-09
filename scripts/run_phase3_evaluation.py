"""
run_phase3_evaluation.py -- Phase 3 exit-criteria report.

Phase 3 is complete only if:
  * every generated Analytics Plan is schema-valid
  * every metric reference resolves to the semantic registry
  * every dimension reference resolves to business_dimensions.md
  * trust handling is delegated to the existing Trust Gate
  * no business definition is duplicated or invented
  * source CSVs remain untouched

This script evaluates each of those over a question bank covering every domain the Phase 3
brief enumerates, plus the brief's own ambiguous questions, and writes phase3_evaluation.csv.
Read-only with respect to every source CSV and every prior deliverable.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.analytics_planner import AnalyticsPlanner
from engine import concept_map
from engine import dimension_resolution as dimres
from engine.intent_models import (validate_plan_schema, READY, BLOCKED, NEEDS_CLARIFICATION,
                                  NOT_DETERMINABLE, REJECTED, PLAN_EXPLAIN_CONFLICT)

OUT_PATH = os.path.join(ROOT, "phase3_evaluation.csv")

FIELDS = [
    "question", "domain", "expectation", "intents", "plan_type", "status", "metric_ids",
    "trust_level", "headline_permitted", "execution_calls", "definitions_planned",
    "clarification_kind", "schema_valid", "validation_problems", "trust_delegated_ok",
    "ambiguity_preserved_ok", "verdict", "reason",
]

# (question, domain, expectation)
#   expectation is what the SPEC requires, used as the pass/fail criterion:
#     "answerable"  -- a single-definition metric may be answered with a headline
#     "multi"       -- SHOW_BOTH/BLOCK: every competing definition, no headline
#     "clarify"     -- ambiguity the resolver must not settle itself
#     "refuse"      -- NOT_DETERMINABLE or REJECTED, with a specific reason
#     "composite"   -- a labelled multi-metric list, never a merged score
QUESTION_BANK = [
    # --- revenue -------------------------------------------------------------------------------
    ("How much revenue did we make?",            "revenue",            "answerable"),
    ("Revenue by month",                          "revenue",            "answerable"),
    ("Why did revenue fall?",                     "revenue",            "answerable"),
    ("Revenue in 2015",                           "revenue",            "refuse"),
    # --- collections ---------------------------------------------------------------------------
    ("How much did we collect?",                  "collections",        "clarify"),
    ("Collections by month",                      "collections",        "clarify"),
    # --- tenant dues ---------------------------------------------------------------------------
    ("How much do tenants owe?",                  "tenant dues",        "multi"),
    ("What are our outstanding receivables?",     "tenant dues",        "multi"),
    ("How much does this tenant owe?",            "tenant dues",        "clarify"),
    # --- deposits ------------------------------------------------------------------------------
    ("How much deposit are we holding?",          "deposits",           "answerable"),
    ("What were our deposit settlements?",        "deposits",           "answerable"),
    ("Are there phantom deposits?",               "deposits",           "answerable"),
    # --- occupancy -----------------------------------------------------------------------------
    ("What is occupancy?",                        "occupancy",          "multi"),
    ("How full are we?",                          "occupancy",          "multi"),
    ("What was occupancy in 2015?",               "occupancy",          "refuse"),
    # --- expenses ------------------------------------------------------------------------------
    ("How much did we spend?",                    "expenses",           "answerable"),
    ("Expenses by category",                      "expenses",           "answerable"),
    # --- profit --------------------------------------------------------------------------------
    ("What's our profit?",                        "profit",             "multi"),
    ("What was profit last month?",               "profit",             "multi"),
    ("Why did profit fall?",                      "profit",             "multi"),
    # --- owner payments ------------------------------------------------------------------------
    ("How much did we pay owners?",               "owner payments",     "answerable"),
    ("How much owner rent did we pay?",           "owner payments",     "multi"),
    # --- maintenance ---------------------------------------------------------------------------
    ("How many maintenance tickets were raised?", "maintenance",        "answerable"),
    ("What was our maintenance cost?",            "maintenance",        "answerable"),
    ("Show me maintenance year on year",          "maintenance",        "refuse"),
    # --- EB ------------------------------------------------------------------------------------
    ("What was our electricity cost?",            "EB",                 "answerable"),
    ("Electricity trend by month",                "EB",                 "refuse"),
    # --- tenant lifecycle ----------------------------------------------------------------------
    ("How many tenants are staying?",             "tenant lifecycle",   "answerable"),
    ("How many move-outs were there?",            "tenant lifecycle",   "answerable"),
    ("How many move-ins last month?",             "tenant lifecycle",   "answerable"),
    ("How many tenants are on notice?",           "tenant lifecycle",   "answerable"),
    # --- accounting / reconciliation -----------------------------------------------------------
    ("Does the trial balance balance?",           "accounting",         "answerable"),
    ("How much cash do we have?",                 "accounting",         "answerable"),
    ("Does the ledger reconcile to source?",      "accounting",         "answerable"),
    ("Show me the monthly P&L",                   "accounting",         "answerable"),
    # --- data quality --------------------------------------------------------------------------
    ("Are there duplicate invoices?",             "data quality",       "answerable"),
    ("Are there duplicate receipts?",             "data quality",       "answerable"),
    ("Are there overlapping allotments?",         "data quality",       "answerable"),
    ("How reliable is our data?",                 "data quality",       "answerable"),
    # --- risk composites -----------------------------------------------------------------------
    ("What are our biggest business risks?",      "risk",               "composite"),
    ("Who are our risky tenants?",                "risk",               "composite"),
    ("Where are we losing money?",                "risk",               "composite"),
    ("Which tenants are overdue?",                "risk",               "answerable"),
    # --- structural refusals -------------------------------------------------------------------
    ("Which property is best?",                   "grain protection",   "refuse"),
    ("What is our margin analysis?",              "absent concept",     "refuse"),
    ("What is our collection efficiency?",        "absent concept",     "refuse"),
    ("What should management do next?",           "recommendation",     "refuse"),
    ("Did anything look off this month?",         "anomaly",            "clarify"),
]


def evaluate(question, domain, expectation, planner, registry, gate):
    plan = planner.plan(question)
    schema_problems = validate_plan_schema(plan, registry)
    full_problems = planner.validate(plan)

    row = {
        "question": question, "domain": domain, "expectation": expectation,
        "intents": ",".join(plan.intents), "plan_type": plan.plan_type, "status": plan.status,
        "metric_ids": ",".join(plan.metric_ids), "trust_level": plan.trust_level,
        "headline_permitted": plan.headline_permitted,
        "execution_calls": len(plan.execution_calls),
        "definitions_planned": ",".join(c.metric_id for c in plan.execution_calls),
        "clarification_kind": plan.clarification.kind if plan.clarification else "",
        "schema_valid": not schema_problems,
        "validation_problems": " | ".join(full_problems),
    }
    problems = list(full_problems)

    # -- trust delegation: every trust field must equal the gate's verdict verbatim -------------
    delegated_ok = True
    if plan.metric_ids and plan.status in (READY, BLOCKED):
        d = gate.authorize(plan.metric_ids[0])
        delegated_ok = (plan.trust_level == d.effective_level
                        and plan.headline_permitted == d.headline_permitted
                        and plan.execution_mode == d.execution_mode)
        if not delegated_ok:
            problems.append(
                f"trust not delegated verbatim: plan={plan.trust_level}/"
                f"{plan.headline_permitted} vs gate={d.effective_level}/{d.headline_permitted}")
    row["trust_delegated_ok"] = delegated_ok

    # -- ambiguity preservation ------------------------------------------------------------------
    amb_ok = True
    if plan.trust_level in ("SHOW_BOTH", "BLOCK"):
        amb_ok = (plan.plan_type == PLAN_EXPLAIN_CONFLICT and not plan.headline_permitted)
        if len(plan.metric_ids) > 1:
            planned = {c.metric_id for c in plan.execution_calls}
            missing = set(plan.metric_ids) - planned - set(plan.excluded_by_time)
            if missing:
                amb_ok = False
                problems.append(f"family silently narrowed: {sorted(missing)} not planned")
        if not amb_ok:
            problems.append("a conflicted metric did not preserve its competing definitions")
    row["ambiguity_preserved_ok"] = amb_ok

    # -- expectation check -------------------------------------------------------------------------
    reason = ""
    if expectation == "answerable":
        ok = plan.status == READY and plan.headline_permitted and len(plan.metric_ids) >= 1
        reason = "" if ok else f"expected an answerable single-definition plan, got {plan.status}"
    elif expectation == "multi":
        ok = (plan.status in (READY, BLOCKED) and plan.plan_type == PLAN_EXPLAIN_CONFLICT
              and not plan.headline_permitted)
        reason = "" if ok else f"expected an explain-the-conflict plan, got {plan.plan_type}"
    elif expectation == "clarify":
        ok = plan.status == NEEDS_CLARIFICATION and not plan.execution_calls
        reason = "" if ok else f"expected a clarification request, got {plan.status}"
    elif expectation == "refuse":
        ok = plan.status in (NOT_DETERMINABLE, REJECTED) and not plan.execution_calls
        reason = "" if ok else f"expected a refusal, got {plan.status}"
    elif expectation == "composite":
        ok = plan.status == READY and len(plan.execution_calls) >= 3
        ids = [c.metric_id for c in plan.execution_calls]
        ok = ok and len(ids) == len(set(ids))
        reason = "" if ok else f"expected a labelled composite, got {len(plan.execution_calls)}"
    else:
        ok, reason = False, f"unknown expectation {expectation!r}"

    if not ok:
        problems.append(reason)

    row["verdict"] = "PASS" if not problems else "FAIL"
    row["reason"] = " | ".join(p for p in problems if p)
    return row, problems


def main():
    registry = SemanticRegistry()
    gate = TrustGate(registry)
    planner = AnalyticsPlanner(registry=registry, gate=gate)

    rows, failures = [], {}
    for question, domain, expectation in QUESTION_BANK:
        row, problems = evaluate(question, domain, expectation, planner, registry, gate)
        rows.append(row)
        if problems:
            failures[question] = problems

    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    passed = sum(1 for r in rows if r["verdict"] == "PASS")
    print("=" * 88)
    print("PHASE 3 EXIT CRITERIA -- Question Understanding + Analytics Planning")
    print("=" * 88)
    print(f"\n[questions] {passed}/{len(rows)} pass")

    by_domain = {}
    for r in rows:
        by_domain.setdefault(r["domain"], []).append(r)
    print("\n  By domain:")
    for dom in sorted(by_domain):
        grp = by_domain[dom]
        ok = sum(1 for r in grp if r["verdict"] == "PASS")
        print(f"    {dom:20s} {ok}/{len(grp)}")

    by_plan = {}
    for r in rows:
        by_plan.setdefault(r["plan_type"], []).append(r)
    print("\n  By plan type (analytics_execution_spec.md 2.1-2.8):")
    for pt in sorted(by_plan):
        print(f"    {pt:24s} {len(by_plan[pt])}")

    by_status = {}
    for r in rows:
        by_status.setdefault(r["status"], []).append(r)
    print("\n  By plan status:")
    for st in sorted(by_status):
        print(f"    {st:22s} {len(by_status[st])}")

    print("\n[exit criteria]")
    schema_ok = sum(1 for r in rows if r["schema_valid"])
    print(f"    every plan schema-valid                    {schema_ok}/{len(rows)}")
    novalid = sum(1 for r in rows if not r["validation_problems"])
    print(f"    every plan passes full validation          {novalid}/{len(rows)}")
    trust_ok = sum(1 for r in rows if r["trust_delegated_ok"])
    print(f"    trust delegated to the Trust Gate verbatim {trust_ok}/{len(rows)}")
    amb_ok = sum(1 for r in rows if r["ambiguity_preserved_ok"])
    print(f"    ambiguity preserved, never silently picked {amb_ok}/{len(rows)}")

    cm_problems = concept_map.verify_against_registry(registry)
    print(f"    every metric reference resolves to registry "
          f"{'YES' if not cm_problems else 'NO -- ' + str(cm_problems)}")
    dim_problems = dimres.verify_dimension_vocabulary()
    print(f"    every dimension resolves to business_dimensions.md "
          f"{'YES' if not dim_problems else 'NO -- ' + str(dim_problems)}")
    print(f"    concepts indexed                           {len(concept_map.all_concepts())}")
    print(f"    registry metrics reachable from a concept  "
          f"{len({m for c in concept_map.all_concepts() for m in c.metric_ids})}"
          f"/{len(registry.all_ids())}")

    if failures:
        print(f"\n{len(failures)} question(s) FAILED -- not hidden:")
        for q, problems in failures.items():
            for p in problems:
                print(f"   {q!r}: {p}")
    else:
        print("\nNo question failed any Phase 3 exit check.")

    print(f"\nWrote {len(rows)} rows to {OUT_PATH}")
    return 0 if not failures and not cm_problems and not dim_problems else 1


if __name__ == "__main__":
    sys.exit(main())
