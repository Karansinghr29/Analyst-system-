"""
build_phase7_registries.py -- generates the Phase 7 structured registries FROM the live system.

The Phase 7 brief asks for "structured registries where useful so specifications cannot drift
from the existing 49-metric semantic registry". Generation is how that guarantee is obtained:
every row below is produced by executing the real engine, so a registry cannot describe a tile,
a role view, or a permission that the system does not actually implement.

Produces:
    owner_dashboard_registry.csv   -- every Owner Dashboard tile, with its render directive
    role_view_registry.csv         -- role x metric, with what each role may and may not conclude
    conflict_disclosure_registry.csv -- the conflicts that must remain visible, and where

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
from engine.execution import MetricExecutor
from engine.bi_contract import BIContractBuilder
from engine.executive_summary import (BUSINESS_HEALTH_KPIS, OPERATIONS_KPIS, RISK_KPIS)
from engine import analyst_roles

DASHBOARD_PATH = os.path.join(ROOT, "owner_dashboard_registry.csv")
ROLE_VIEW_PATH = os.path.join(ROOT, "role_view_registry.csv")
CONFLICT_PATH = os.path.join(ROOT, "conflict_disclosure_registry.csv")

NOT_DET = "Not determinable from exported evidence."

# Owner Dashboard sections, and the metrics each draws on. Every metric_id here already exists
# in semantic_metric_registry.csv -- the dashboard introduces no KPI of its own, which is the
# Phase 7 constraint "Do NOT invent unsupported KPIs".
DASHBOARD_SECTIONS = (
    ("Business Health", BUSINESS_HEALTH_KPIS),
    ("Operations", OPERATIONS_KPIS),
    ("Risks", RISK_KPIS),
)

# What a tile is permitted to render, derived from the trust level. This is the dashboard's
# contract, not a styling preference: a BI tool's native idiom is one number per tile, and that
# idiom is exactly what a SHOW_BOTH/BLOCK metric must not be rendered into.
RENDER_RULES = {
    "SAFE": ("kpi_card", "Single value with its validation status."),
    "DISCLOSE": ("kpi_card_with_caveat",
                 "Single value; the caveat is rendered WITH the number, never behind a tooltip "
                 "the owner may not open."),
    "SHOW_BOTH": ("multi_definition_panel",
                  "Every competing definition, separately labelled, plus the numeric spread. "
                  "No single figure, no default, no average."),
    "BLOCK": ("conflict_panel_no_headline",
              "No headline figure at all. The panel explains why, names the conflicts, lists "
              "each definition's own value, and surfaces the owner decision required."),
    "NOT_DETERMINABLE": ("not_determinable_notice",
                         f'The exact sentence "{NOT_DET}" plus what specifically is missing. '
                         f"No chart, no placeholder, no zero."),
}


def build_dashboard_registry(registry, gate, bi):
    rows = []
    for section, metric_ids in DASHBOARD_SECTIONS:
        for mid in metric_ids:
            spec = registry.get(mid)
            card = bi.card(mid)
            widget, rule = RENDER_RULES[card.trust_level]
            rows.append({
                "section": section,
                "metric_id": mid,
                "display_name": spec.display_name or spec.semantic_name,
                "domain": spec.domain,
                "trust_level": card.trust_level,
                "headline_permitted": card.headline_permitted,
                "widget": widget,
                "render_rule": rule,
                "render_directive": card.render_directive,
                "definition_count": len(card.definitions),
                "conflict_ids": ";".join(card.conflicts),
                "dq_ids": ";".join(card.dq_issues),
                "validation_status": card.validation_status,
                "confidence": card.confidence,
                "evidence": ";".join(str(e) for e in card.evidence[:5]),
                "drilldown_available": bool(card.dimensions),
                "caveat": (card.caveat or "")[:200],
            })
    return rows


# What each role may CONCLUDE, and what it must NEVER claim. Derived from the role's own
# never_does boundary plus the trust level of the metric in question -- so a permission can
# never be looser than the trust policy allows.
def permitted_conclusion(trust_level, role):
    if trust_level == "SAFE":
        return "State the value as the answer, with its evidence and validation status."
    if trust_level == "DISCLOSE":
        return "State the value, with the documented caveat carried alongside it."
    if trust_level == "SHOW_BOTH":
        return ("Present every competing definition and the spread between them. May explain "
                "why they differ; may NOT select one.")
    if trust_level == "BLOCK":
        return ("Explain why no single figure exists, present each definition separately, and "
                "surface the owner decision. May NOT state a headline figure.")
    return f'State exactly: "{NOT_DET}", plus what is missing.'


def forbidden_claim(trust_level, role):
    base = role.never_does
    if trust_level in ("SHOW_BOTH", "BLOCK"):
        return (f"{base} Additionally: no single figure, no default definition, no average of "
                f"the competing values, and no recommendation acting on a disputed number.")
    if trust_level == "NOT_DETERMINABLE":
        return f"{base} Additionally: no estimate, no proxy metric, no zero-as-placeholder."
    if trust_level == "DISCLOSE":
        return f"{base} Additionally: the caveat may not be dropped for brevity."
    return base


def build_role_view_registry(registry, gate):
    rows = []
    for role in analyst_roles.all_roles():
        for mid in registry.all_ids():
            spec = registry.get(mid)
            if spec.domain not in role.domains:
                continue
            trust = gate.authorize(mid).effective_level
            rows.append({
                "role_id": role.role_id,
                "role_display_name": role.display_name,
                "metric_id": mid,
                "metric_name": spec.semantic_name,
                "domain": spec.domain,
                "trust_level": trust,
                "headline_permitted": trust in ("SAFE", "DISCLOSE"),
                "dimensions": spec.dimensions[:160],
                "date_field": spec.date_field[:120],
                "permitted_conclusion": permitted_conclusion(trust, role),
                "must_never_claim": forbidden_claim(trust, role),
                "conflict_ids": ";".join(spec.conflict_ids),
                "dq_ids": ";".join(spec.dq_ids),
                "validation_reference": spec.validation_reference[:160],
            })
    return rows


def build_conflict_registry(registry, gate, executor):
    """Every conflict that must remain visible, and the surfaces it must remain visible ON."""
    rows = []
    seen = set()
    for mid in registry.all_ids():
        spec = registry.get(mid)
        trust = gate.authorize(mid).effective_level
        if trust not in ("SHOW_BOTH", "BLOCK"):
            continue
        answer = executor.execute(mid)
        key = (tuple(spec.conflict_ids), mid)
        if key in seen:
            continue
        seen.add(key)
        # A metric can be SHOW_BOTH/BLOCK yet have no computable definitions: M.OCC.005
        # (historical, day-weighted occupancy) carries a documented conflict, but its Def E
        # calculation is out of Phase 1 scope, so executing it returns nothing. The conflict is
        # still real and still must be disclosed -- what changes is that the surfaces show the
        # conflict WITHOUT figures, rather than pretending two numbers exist to compare.
        computable = len(answer.results)
        rows.append({
            "metric_id": mid,
            "metric_name": spec.semantic_name,
            "trust_level": trust,
            "conflict_ids": ";".join(spec.conflict_ids),
            "dq_ids": ";".join(spec.dq_ids),
            "competing_definitions": computable,
            "definitions_computable": computable >= 2,
            "definition_labels": (" | ".join(r.definition_label for r in answer.results)
                                  or f"none computable -- {NOT_DET}"),
            "must_appear_on": ("owner_dashboard;role_views;bi_cards;executive_summary;"
                               "insight_feed;decision_queue;conversation_answers"),
            "headline_permitted_anywhere": False,
            "resolution_owner": "business owner (not the system)",
            "resolution_note": (
                "Only an owner decision can settle which definition is authoritative. Until "
                "then every surface shows all of them."
                + ("" if computable >= 2 else
                   " NOTE: this metric's competing definitions are not computable in the "
                   "current engine, so surfaces disclose the conflict WITHOUT figures rather "
                   f"than implying two comparable numbers exist. {NOT_DET}")),
        })
    return rows


def write(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    registry = SemanticRegistry()
    gate = TrustGate(registry)
    executor = MetricExecutor(registry=registry, gate=gate)
    bi = BIContractBuilder(registry, gate, executor)

    dash = build_dashboard_registry(registry, gate, bi)
    write(DASHBOARD_PATH, dash, list(dash[0]))

    roles = build_role_view_registry(registry, gate)
    write(ROLE_VIEW_PATH, roles, list(roles[0]))

    conflicts = build_conflict_registry(registry, gate, executor)
    write(CONFLICT_PATH, conflicts, list(conflicts[0]))

    n_blocked = sum(1 for r in dash if not r["headline_permitted"])
    print(f"owner_dashboard_registry.csv   {len(dash)} tiles "
          f"({n_blocked} may NOT render a headline)")
    print(f"role_view_registry.csv         {len(roles)} role/metric views "
          f"across {len(analyst_roles.ALL_ROLES)} roles")
    print(f"conflict_disclosure_registry.csv {len(conflicts)} conflicts that must stay visible")
    return 0


if __name__ == "__main__":
    sys.exit(main())
