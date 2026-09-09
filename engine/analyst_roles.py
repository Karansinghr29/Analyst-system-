"""
analyst_roles.py -- Phase 6. Analyst-lens registry and deterministic role routing.

ai_agent_roles.md 1 already settles the central design question, and this module implements its
answer rather than inventing a parallel one:

    "The brief asks for a system that behaves as a combination of Data Analyst, Data Scientist,
     BI Analyst, Business Analyst, Financial Analyst, and Operations Analyst. These are **not**
     six separate functional roles to implement -- they are six **domain lenses** the same
     underlying functional pipeline must be able to apply, because each lens draws on a
     different slice of the same semantic layer."

So a lens selects WHICH already-existing semantic content is foregrounded. It never changes a
calculation, a trust verdict, or a definition. Routing is deterministic: a lens is derived from
the resolved metric's `domain` column and the question's intent, both of which already exist.
No lens can introduce a metric, and `verify_against_registry()` fails loudly if one tries.

The owner never selects a lens. ai_agent_roles.md 1: "A single question may require multiple
lenses simultaneously" -- so routing returns a set, ordered by how directly each lens applies.
"""
from dataclasses import dataclass, field

from engine.semantic_registry import SemanticRegistry
from engine.intent_models import (LOOKUP, FILTERED_LOOKUP, TREND, COMPARISON, ANOMALY, DRIVER,
                                  RISK_SCAN, RECOMMENDATION, META)

# --- Lens identifiers ---------------------------------------------------------------------------

DATA_ANALYST = "data_analyst"
BUSINESS_ANALYST = "business_analyst"
FINANCIAL_ANALYST = "financial_analyst"
OPERATIONS_ANALYST = "operations_analyst"
DATA_SCIENTIST = "data_scientist"
BI_ANALYST = "bi_analyst"
MANAGEMENT_REPORTING = "management_reporting_analyst"
DECISION_SUPPORT = "decision_support_analyst"
RISK_DQ_ANALYST = "risk_dq_analyst"

ALL_ROLES = (DATA_ANALYST, BUSINESS_ANALYST, FINANCIAL_ANALYST, OPERATIONS_ANALYST,
             DATA_SCIENTIST, BI_ANALYST, MANAGEMENT_REPORTING, DECISION_SUPPORT,
             RISK_DQ_ANALYST)

# The six lenses ai_agent_roles.md 1 names directly. The other three are Phase 6 compositions of
# machinery that already exists (insight ranking, decision support, the DQ register) rather than
# new domain knowledge -- recorded here so the distinction stays visible.
SPEC_DEFINED_ROLES = (DATA_ANALYST, DATA_SCIENTIST, BI_ANALYST, BUSINESS_ANALYST,
                      FINANCIAL_ANALYST, OPERATIONS_ANALYST)
PHASE6_COMPOSED_ROLES = (MANAGEMENT_REPORTING, DECISION_SUPPORT, RISK_DQ_ANALYST)


@dataclass(frozen=True)
class AnalystRole:
    role_id: str
    display_name: str
    source: str                 # the document that defines this lens
    semantic_scope: str         # which slice of the semantic layer it draws on
    capabilities: tuple         # capability ids, resolved against analysis_capability_registry
    domains: tuple = ()         # registry `domain` values this lens owns
    intents: tuple = ()         # intents that summon this lens regardless of domain
    never_does: str = ""


# `domains` values are the registry's OWN `domain` column values, so a lens can never claim a
# metric the registry does not place in its domain.
ROLES = (
    AnalystRole(
        role_id=DATA_ANALYST, display_name="Data Analyst",
        source="ai_agent_roles.md 1",
        semantic_scope="Any metric -- raw lookups, filters, groupings.",
        capabilities=("kpi_lookup", "trend", "period_comparison", "segmentation",
                      "dimensional_analysis", "anomaly_surface", "data_quality_check",
                      "metric_reconciliation", "drill_down", "root_cause_exploration"),
        domains=("Financial", "Operations", "Risk & Data Quality"),
        intents=(LOOKUP, FILTERED_LOOKUP, TREND, COMPARISON),
        never_does="Introduce a metric, dimension, or grouping the semantic layer does not "
                   "already document.",
    ),
    AnalystRole(
        role_id=BUSINESS_ANALYST, display_name="Business Analyst",
        source="ai_agent_roles.md 1",
        semantic_scope="Cross-cutting synthesis, risk scans, recommendations.",
        capabilities=("business_performance", "operational_efficiency", "business_risk_scan",
                      "recommendation", "cross_domain_synthesis"),
        domains=("Financial", "Operations"),
        intents=(RISK_SCAN, RECOMMENDATION),
        never_does="Blend competing definitions into one business conclusion.",
    ),
    AnalystRole(
        role_id=FINANCIAL_ANALYST, display_name="Financial Analyst",
        source="ai_agent_roles.md 1 (semantic_layer.md 1-6, 10-16)",
        semantic_scope="Revenue, collections, invoices, AR, deposits, expenses, owner payments, "
                       "profit, ledger, cash.",
        capabilities=("pnl", "revenue_analysis", "expense_analysis", "collections_analysis",
                      "ar_analysis", "deposit_analysis", "ledger_analysis", "cash_movement",
                      "owner_payment_analysis", "reconciliation", "accounting_consistency"),
        domains=("Financial",),
        never_does="State a single financial truth where the evidence carries competing "
                   "definitions. Every conflict is preserved, never resolved.",
    ),
    AnalystRole(
        role_id=OPERATIONS_ANALYST, display_name="Operations Analyst",
        source="ai_agent_roles.md 1 (semantic_layer.md 7-9, 13-14)",
        semantic_scope="Occupancy, tenants, lifecycle, maintenance, EB.",
        capabilities=("occupancy_analysis", "bed_utilization", "tenant_lifecycle",
                      "maintenance_analysis", "eb_analysis", "operational_utilization"),
        domains=("Operations",),
        never_does="Present a bed/apartment-grain figure the evidence cannot support.",
    ),
    AnalystRole(
        role_id=DATA_SCIENTIST, display_name="Data Scientist / Diagnostic Analyst",
        source="ai_agent_roles.md 1",
        semantic_scope="Trend/anomaly/driver analysis across any domain.",
        capabilities=("trend_break", "driver_analysis", "relationship_analysis",
                      "pattern_discovery", "statistical_summary",
                      "revenue_forecast", "forecast_scenario",
                      "descriptive_analysis"),
        domains=("Financial", "Operations", "Risk & Data Quality"),
        intents=(ANOMALY, DRIVER),
        never_does="Apply a statistical method or threshold the specifications do not define. "
                   "analytics_execution_spec.md 2.5 leaves the anomaly method open, so no "
                   "anomaly threshold is invented here.",
    ),
    AnalystRole(
        role_id=BI_ANALYST, display_name="BI Analyst",
        source="ai_agent_roles.md 1",
        semantic_scope="Cross-domain dashboards, KPI composition.",
        capabilities=("kpi_card", "trend_view", "period_comparison_view", "breakdown_view",
                      "filter", "drilldown", "dashboard_narrative", "metric_definition_surface",
                      "data_quality_indicator"),
        domains=("Financial", "Operations", "Risk & Data Quality"),
        never_does="Emit a KPI card without its trust level, conflicts, and DQ indicators.",
    ),
    AnalystRole(
        role_id=MANAGEMENT_REPORTING, display_name="Management Reporting Analyst",
        source="Phase 6 composition of business_insight_framework.md Part A + "
               "answer_contract.md",
        semantic_scope="Executive summary assembly across every domain.",
        capabilities=("executive_summary", "management_briefing", "what_changed"),
        domains=("Financial", "Operations", "Risk & Data Quality"),
        never_does="Collapse a SHOW_BOTH/BLOCK metric into a single headline KPI for brevity.",
    ),
    AnalystRole(
        role_id=DECISION_SUPPORT, display_name="Decision-Support Analyst",
        source="Phase 6 composition of business_reasoning_spec.md + decision_support.py",
        semantic_scope="Recommendations and pending owner decisions.",
        capabilities=("recommendation", "attention_required", "pending_decision",
                      "investigation_priority"),
        domains=("Financial", "Operations", "Risk & Data Quality"),
        intents=(RECOMMENDATION,),
        never_does="Recommend an operational action on a BLOCK metric's disputed figure; the "
                   "only recommendation available there is to resolve the conflict.",
    ),
    AnalystRole(
        role_id=RISK_DQ_ANALYST, display_name="Risk / Data-Quality Analyst",
        source="Phase 6 composition of data_quality_report.md + insight_generation_spec.md",
        semantic_scope="The DQ register, conflicts, and trust posture.",
        capabilities=("dq_scan", "conflict_surface", "trust_advisory", "risk_ranking"),
        domains=("Risk & Data Quality",),
        intents=(RISK_SCAN,),
        never_does="Manufacture urgency for a LOW/INFORMATIONAL finding "
                   "(ai_agent_roles.md 2, Insight Generator).",
    ),
)

_BY_ID = {r.role_id: r for r in ROLES}


def role(role_id):
    return _BY_ID.get(role_id)


def all_roles():
    return ROLES


# --- Routing --------------------------------------------------------------------------------------

# Intent -> lenses that always apply, independent of which metric resolved. Derived from
# ai_agent_roles.md 1's "Primarily engages" column and question_understanding_spec.md 2.
_INTENT_ROLES = {
    LOOKUP: (DATA_ANALYST,),
    FILTERED_LOOKUP: (DATA_ANALYST,),
    TREND: (DATA_ANALYST, BI_ANALYST),
    COMPARISON: (DATA_ANALYST, BI_ANALYST),
    ANOMALY: (DATA_SCIENTIST, DATA_ANALYST),
    DRIVER: (DATA_SCIENTIST, BUSINESS_ANALYST),
    RISK_SCAN: (RISK_DQ_ANALYST, BUSINESS_ANALYST),
    RECOMMENDATION: (DECISION_SUPPORT, BUSINESS_ANALYST),
    META: (RISK_DQ_ANALYST,),
}

_DOMAIN_ROLES = {
    "Financial": (FINANCIAL_ANALYST,),
    "Operations": (OPERATIONS_ANALYST,),
    "Risk & Data Quality": (RISK_DQ_ANALYST,),
}


@dataclass(frozen=True)
class RoleRouting:
    roles: tuple                # ordered, most directly applicable first
    reasons: dict               # role_id -> why it was routed
    primary: str = ""

    def explain(self):
        return tuple(f"{r} ({self.reasons.get(r, '')})" for r in self.roles)


def route(intents=(), metric_ids=(), registry: SemanticRegistry = None,
          trust_level="", structural_limitation=False):
    """Deterministically select the analyst lenses a question needs.

    Ordering is by directness: the domain lens of the metric actually answered comes first,
    then intent-driven lenses, then the trust/conflict lens when a conflict is in play. The set
    is never empty -- every question is at minimum a Data Analyst lookup.
    """
    registry = registry or SemanticRegistry()
    ordered, reasons = [], {}

    def add(role_id, why):
        if role_id not in reasons:
            ordered.append(role_id)
            reasons[role_id] = why
        elif why not in reasons[role_id]:
            reasons[role_id] = f"{reasons[role_id]}; {why}"

    # 1. The domain of the metric that actually answered -- the most direct lens.
    for mid in metric_ids:
        if mid in registry:
            domain = registry.get(mid).domain
            for r in _DOMAIN_ROLES.get(domain, ()):
                add(r, f"{mid} is in the {domain} domain")

    # 2. Intent-driven lenses.
    for intent in intents:
        for r in _INTENT_ROLES.get(intent, ()):
            add(r, f"intent={intent}")

    # 3. A conflicted or caveated metric always summons the risk/DQ lens: the conflict is part
    #    of the answer, not an aside (ai_trust_policy.md 2).
    if trust_level in ("SHOW_BOTH", "BLOCK", "DISCLOSE"):
        add(RISK_DQ_ANALYST, f"trust_level={trust_level} requires disclosure")

    # 4. A structural limitation (the degenerate-property case) is a BI/business framing
    #    question, not an analytical one -- the answer is about what the data can support.
    if structural_limitation:
        add(BI_ANALYST, "the question asks for a view the data's structure cannot support")
        add(BUSINESS_ANALYST, "the limitation is a business fact, not a calculation failure")

    if not ordered:
        add(DATA_ANALYST, "default lens: every question is at minimum a lookup")

    return RoleRouting(roles=tuple(ordered), reasons=reasons, primary=ordered[0])


def capabilities_for(role_ids):
    out = []
    for rid in role_ids:
        r = _BY_ID.get(rid)
        if r:
            for c in r.capabilities:
                if c not in out:
                    out.append(c)
    return tuple(out)


def verify_against_registry(registry: SemanticRegistry = None):
    """Guard: a lens may only claim domains the registry actually uses, and every registry
    domain must be owned by at least one lens or metrics would be unreachable."""
    registry = registry or SemanticRegistry()
    problems = []
    registry_domains = {registry.get(m).domain for m in registry.all_ids()}

    for r in ROLES:
        for d in r.domains:
            if d not in registry_domains:
                problems.append(f"{r.role_id} claims domain {d!r}, which no metric uses")
        if not r.capabilities:
            problems.append(f"{r.role_id} declares no capabilities")
        if not r.source:
            problems.append(f"{r.role_id} cites no defining document")

    covered = {d for r in ROLES for d in r.domains}
    for d in registry_domains:
        if d not in covered:
            problems.append(f"registry domain {d!r} is owned by no analyst lens")
    return problems
