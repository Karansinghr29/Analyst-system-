"""
build_question_catalog.py -- generates business_question_catalog.md by running each catalogued
question through the real system.

Generated rather than written by hand, so the catalog states what the system ACTUALLY does
rather than what it was intended to do. A question whose behaviour changes shows up here the
next time this runs.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.analyst_intelligence import AnalystIntelligence
from engine.semantic_registry import SemanticRegistry
from engine.result import NOT_DETERMINABLE_TEXT

OUT = os.path.join(ROOT, "business_question_catalog.md")

# (question, business area) -- the Phase 6 brief's own list, plus the owner-language variants.
QUESTIONS = [
    ("What is today's occupancy?", "Occupancy"),
    ("How many tenants are staying?", "Tenant lifecycle"),
    ("How many are on notice?", "Tenant lifecycle"),
    ("What is revenue this month?", "Revenue"),
    ("How much did we collect?", "Collections"),
    ("How much do tenants owe?", "Receivables"),
    ("Which tenants have outstanding dues?", "Receivables"),
    ("Why did collections fall?", "Collections"),
    ("Why did profit fall?", "Profit"),
    ("Which expense category is largest?", "Expenses"),
    ("How much owner payment was made?", "Owner payments"),
    ("How much deposit is held?", "Deposits"),
    ("How many deposits are unresolved?", "Deposits"),
    ("Which apartments are under-utilized?", "Occupancy"),
    ("Which property is performing better?", "Cross-domain"),
    ("Which month had the highest revenue?", "Revenue"),
    ("Which month had the highest profit?", "Profit"),
    ("What are our biggest financial risks?", "Risk"),
    ("What data problems should I know about?", "Data quality"),
    ("Which numbers should I trust?", "Data quality"),
    ("What changed this month?", "Cross-domain"),
    ("What requires my decision?", "Decision support"),
    ("What should I investigate first?", "Decision support"),
    ("How many maintenance tickets were raised?", "Maintenance"),
    ("What was our electricity cost?", "EB / electricity"),
    ("Does the trial balance balance?", "Accounting"),
    ("How much cash do we have?", "Cash"),
    ("Why are dues increasing?", "Receivables"),
    ("Why is occupancy low?", "Occupancy"),
    ("How is the business doing?", "Cross-domain"),
]


def shape_of(a):
    if a.owner_intent != "metric_question":
        return {"briefing": "Management briefing",
                "what_changed": "Period-change list",
                "what_to_do": "Decision list",
                "what_to_trust": "Trust posture list"}[a.owner_intent]
    r = a.ask_result
    if r is None:
        return "No plan"
    if r.status == "NEEDS_CLARIFICATION":
        return "Clarification request"
    if r.status in ("NOT_DETERMINABLE", "REJECTED"):
        return "Refusal with reason"
    if r.trust_level in ("SHOW_BOTH", "BLOCK"):
        n = len(r.answers[0].results) if r.answers else 0
        return f"All {n} competing definitions, no headline"
    return "Single value"


def main():
    reg = SemanticRegistry()
    ai = AnalystIntelligence(registry=reg)

    rows = []
    for q, area in QUESTIONS:
        a = ai.ask(q)
        ai.reset()
        r = a.ask_result
        plan = r.plan if r is not None else None

        rows.append({
            "question": q,
            "area": area,
            "intent": ",".join(plan.intents) if plan else a.owner_intent,
            "roles": ", ".join(a.routing.roles[:3]) if a.routing else "",
            "metrics": ", ".join(a.metric_ids[:4]) or "—",
            "trust": a.trust_level or "—",
            "shape": shape_of(a),
            "recommendation_eligible": bool(
                plan and plan.decision_requested) or a.owner_intent == "what_to_do",
            "determinable": not (r is not None and r.status in ("NOT_DETERMINABLE",)),
            "limitations": " ".join(a.limitations)[:200],
        })

    lines = [
        "# Business Question Catalog",
        "",
        "**Generated** by `scripts/build_question_catalog.py`, which runs every question through",
        "the real system. This records what the system *does*, not what it was intended to do.",
        "",
        "For each question: the intent it resolves to, the analyst lenses routed, the metrics",
        "answered, the trust posture, the shape of the answer, and whether a recommendation is",
        "eligible. Where the registry cannot answer, the entry says so with the exact phrase",
        f'**"{NOT_DETERMINABLE_TEXT}"**',
        "",
        "No definition is invented here. Every `metric_id` below already exists in",
        "`semantic_metric_registry.csv`.",
        "",
        "---",
        "",
        "## Coverage summary",
        "",
    ]

    total = len(rows)
    answered = sum(1 for r in rows if r["shape"] in ("Single value",)
                   or r["shape"].startswith("All "))
    multi = sum(1 for r in rows if r["shape"].startswith("All "))
    clarify = sum(1 for r in rows if r["shape"] == "Clarification request")
    refuse = sum(1 for r in rows if r["shape"] == "Refusal with reason")
    workflow = total - answered - clarify - refuse

    lines += [
        "| Outcome | Count |",
        "|---|---|",
        f"| Questions catalogued | {total} |",
        f"| Answered with a single value | {answered - multi} |",
        f"| Answered with competing definitions (no headline) | {multi} |",
        f"| Routed to a whole-business workflow | {workflow} |",
        f"| Clarification required (never guessed) | {clarify} |",
        f"| Refused with a stated reason | {refuse} |",
        "",
        "---",
        "",
        "## Catalog",
        "",
        "| Question | Area | Intent | Analyst lenses | Metrics | Trust | Answer shape | Rec. eligible |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['question']} | {r['area']} | {r['intent']} | {r['roles']} | "
            f"`{r['metrics']}` | {r['trust']} | {r['shape']} | "
            f"{'yes' if r['recommendation_eligible'] else 'no'} |")

    limited = [r for r in rows if r["limitations"]]
    if limited:
        lines += ["", "---", "", "## Stated limitations", ""]
        for r in limited:
            lines.append(f"- **{r['question']}** — {r['limitations']}")

    lines += [
        "",
        "---",
        "",
        "## Questions the registry cannot answer",
        "",
        "These are **structurally absent**, not failures. `question_understanding_spec.md` §3.3:",
        "the resolver must recognise them as absent rather than improvising from adjacent",
        "metrics.",
        "",
    ]
    for r in rows:
        if r["shape"] == "Refusal with reason":
            lines.append(f"- **{r['question']}** — {NOT_DETERMINABLE_TEXT}")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"catalogued {total} questions -> {OUT}")
    print(f"  single value {answered - multi} | multi-definition {multi} | "
          f"workflow {workflow} | clarify {clarify} | refuse {refuse}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
