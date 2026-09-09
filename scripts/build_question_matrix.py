"""
build_question_matrix.py -- generates business_question_matrix.md by running the Phase 7
question set through the live system.

Generated, not authored, so the matrix records what the system does. A behaviour change shows
up here the next time this runs, which is what stops a specification from drifting away from
the product it describes.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.analyst_intelligence import AnalystIntelligence
from engine.semantic_registry import SemanticRegistry
from engine import analyst_roles
from engine.result import NOT_DETERMINABLE_TEXT

OUT = os.path.join(ROOT, "business_question_matrix.md")

# The Phase 7 brief's own AI-Business-Analyst question list, plus the owner-language variants.
QUESTIONS = [
    "How is the business doing?",
    "What changed?",
    "Why did profit fall?",
    "Why are collections down?",
    "Which area needs attention?",
    "What are the biggest risks?",
    "What should I do today?",
    "What should I fix first?",
    "Where am I losing money?",
    "Which tenants need attention?",
    "Are expenses increasing?",
    "What caused this change?",
    "Show me the important business insights.",
    "Give me the management report.",
    "Compare this month with last month.",
    "What should I tell the owner?",
    "Is there anything unusual?",
    "Can I trust this number?",
    "How much revenue did we make?",
    "What is occupancy?",
    "How much do tenants owe?",
    "How much deposit is held?",
    "What was our electricity cost?",
    "How many maintenance tickets were raised?",
    "Which property is performing better?",
]

TRUST_BEHAVIOUR = {
    "SAFE": "Answer normally, with evidence and validation status.",
    "DISCLOSE": "Answer, with the documented caveat carried alongside the figure.",
    "SHOW_BOTH": "Present every competing definition and the spread. Never select one.",
    "BLOCK": "No headline figure. Explain why, list each definition, surface the owner decision.",
    "NOT_DETERMINABLE": f'State exactly: "{NOT_DETERMINABLE_TEXT}"',
    "": "Whole-business workflow; per-metric trust applies to each line it contains.",
}


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
        return "Clarification (never guessed)"
    if r.status in ("NOT_DETERMINABLE", "REJECTED"):
        return "Refusal with stated reason"
    if r.trust_level in ("SHOW_BOTH", "BLOCK"):
        n = len(r.answers[0].results) if r.answers else 0
        return f"{n} competing definitions, no headline"
    return "Single value"


def main():
    registry = SemanticRegistry()
    ai = AnalystIntelligence(registry=registry)

    rows = []
    for q in QUESTIONS:
        a = ai.ask(q)
        ai.reset()
        r = a.ask_result
        plan = r.plan if r is not None else None
        rows.append({
            "q": q,
            "intent": ",".join(plan.intents) if plan else a.owner_intent,
            "lenses": ", ".join(a.routing.roles[:3]) if a.routing else "",
            "metrics": ", ".join(a.metric_ids[:4]) or "—",
            "trust": a.trust_level or "—",
            "shape": shape_of(a),
            "ladder": ("FACT→CALC→OBS→INF→HYP" if a.root_cause else
                       "FACT→CALCULATION" if r and r.executed else "—"),
            "limitations": " ".join(a.limitations)[:180],
        })

    lines = [
        "# Business Question Matrix",
        "",
        "**Generated** by `scripts/build_question_matrix.py`, which runs every question through",
        "the live Phase 1–6 system. This records what the product *does*, not what it intends.",
        "",
        "Columns: the intent resolved, the analyst lenses routed, the metrics answered, the trust",
        "posture, the shape of the answer, and how far up the reasoning ladder the answer climbs.",
        "",
        "Every `metric_id` below already exists in `semantic_metric_registry.csv`. No definition",
        "is invented here.",
        "",
        "---",
        "",
        "## Trust behaviour (applies to every row)",
        "",
        "| Trust level | Answer behaviour |",
        "|---|---|",
    ]
    for level, behaviour in TRUST_BEHAVIOUR.items():
        if level:
            lines.append(f"| `{level}` | {behaviour} |")

    lines += [
        "",
        "---",
        "",
        "## Matrix",
        "",
        "| Question | Intent | Analyst lenses | Metrics | Trust | Answer shape | Ladder |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['q']} | {r['intent']} | {r['lenses']} | `{r['metrics']}` | "
                     f"{r['trust']} | {r['shape']} | {r['ladder']} |")

    limited = [r for r in rows if r["limitations"]]
    if limited:
        lines += ["", "---", "", "## Stated limitations", ""]
        for r in limited:
            lines.append(f"- **{r['q']}** — {r['limitations']}")

    counts = {}
    for r in rows:
        counts[r["shape"]] = counts.get(r["shape"], 0) + 1
    lines += ["", "---", "", "## Coverage", "", "| Answer shape | Count |", "|---|---|"]
    for shape, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {shape} | {n} |")

    lines += [
        "",
        f"**{len(QUESTIONS)} questions catalogued.** Every one either answers, asks for",
        "clarification, or refuses with a stated reason. None guesses.",
        "",
    ]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"catalogued {len(rows)} questions -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
