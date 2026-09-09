"""
build_analyst_registries.py -- generates analyst_role_registry.csv and
analysis_capability_registry.csv FROM the code that implements them.

Generated rather than hand-written so the registries cannot drift from the engine: a lens or
capability that exists only in a CSV, or only in code, is caught the next time this runs.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import analyst_roles as ar
from engine.semantic_registry import SemanticRegistry

ROLE_PATH = os.path.join(ROOT, "analyst_role_registry.csv")
CAP_PATH = os.path.join(ROOT, "analysis_capability_registry.csv")

NOT_DET = "Not determinable from exported evidence."

# capability_id -> (defining document, implementing module, status)
CAP_IMPL = {
    "kpi_lookup": ("analytics_execution_spec.md 2.1", "engine/execution.py", "IMPLEMENTED"),
    "trend": ("analytics_execution_spec.md 2.4", "engine/analytics_planner.py", "IMPLEMENTED"),
    "period_comparison": ("analytics_execution_spec.md 2.3", "engine/change_detection.py",
                          "IMPLEMENTED"),
    "segmentation": ("analytics_execution_spec.md 2.2", "engine/dimension_resolution.py",
                     "IMPLEMENTED"),
    "dimensional_analysis": ("business_dimensions.md", "engine/dimension_resolver.py",
                             "IMPLEMENTED"),
    "anomaly_surface": ("analytics_execution_spec.md 2.5", "engine/analytics_planner.py",
                        "PARTIAL"),
    "data_quality_check": ("data_quality_report.md", "engine/insight_engine.py", "IMPLEMENTED"),
    "metric_reconciliation": ("analytics_execution_spec.md 8", "engine/validator.py",
                              "IMPLEMENTED"),
    "drill_down": ("analytics_execution_spec.md 2.2", "engine/analytics_planner.py",
                   "IMPLEMENTED"),
    "root_cause_exploration": ("analytics_execution_spec.md 2.6", "engine/root_cause.py",
                               "IMPLEMENTED"),
    "business_performance": ("business_insight_framework.md Part A",
                             "engine/executive_summary.py", "IMPLEMENTED"),
    "operational_efficiency": ("semantic_layer.md 7-9", "engine/executive_summary.py",
                               "IMPLEMENTED"),
    "business_risk_scan": ("analytics_execution_spec.md 2.8", "engine/analytics_planner.py",
                           "IMPLEMENTED"),
    "recommendation": ("business_reasoning_spec.md 2", "engine/business_reasoning.py",
                       "IMPLEMENTED"),
    "cross_domain_synthesis": ("ai_agent_roles.md 1", "engine/analyst_intelligence.py",
                               "IMPLEMENTED"),
    "pnl": ("semantic_layer.md 12", "engine/calculators/financial.py", "IMPLEMENTED"),
    "revenue_analysis": ("semantic_layer.md 1", "engine/calculators/financial.py",
                         "IMPLEMENTED"),
    "expense_analysis": ("semantic_layer.md 10", "engine/calculators/financial.py",
                         "IMPLEMENTED"),
    "collections_analysis": ("semantic_layer.md 2", "engine/calculators/collections_.py",
                             "IMPLEMENTED"),
    "ar_analysis": ("semantic_layer.md 4", "engine/calculators/receivables.py", "IMPLEMENTED"),
    "deposit_analysis": ("semantic_layer.md 5", "engine/calculators/deposits.py",
                         "IMPLEMENTED"),
    "ledger_analysis": ("semantic_layer.md 15", "engine/calculators/ledger.py", "IMPLEMENTED"),
    "cash_movement": ("semantic_layer.md 16", "engine/calculators/financial.py", "IMPLEMENTED"),
    "owner_payment_analysis": ("semantic_layer.md 11", "engine/calculators/financial.py",
                               "IMPLEMENTED"),
    "reconciliation": ("semantic_layer.md 15", "engine/calculators/risk_dq.py", "IMPLEMENTED"),
    "accounting_consistency": ("business_dimensions.md 21", "engine/validator.py",
                               "IMPLEMENTED"),
    "occupancy_analysis": ("semantic_layer.md 7", "engine/calculators/occupancy.py",
                           "IMPLEMENTED"),
    "bed_utilization": ("semantic_layer.md 7", "engine/calculators/occupancy.py", "PARTIAL"),
    "tenant_lifecycle": ("semantic_layer.md 9", "engine/calculators/occupancy.py",
                         "IMPLEMENTED"),
    "maintenance_analysis": ("semantic_layer.md 13", "engine/calculators/maintenance.py",
                             "IMPLEMENTED"),
    "eb_analysis": ("semantic_layer.md 14", "engine/calculators/eb.py", "IMPLEMENTED"),
    "operational_utilization": ("semantic_layer.md 7-8", "engine/calculators/occupancy.py",
                                "IMPLEMENTED"),
    "trend_break": ("analytics_execution_spec.md 2.5", "engine/change_detection.py", "PARTIAL"),
    "driver_analysis": ("analytics_execution_spec.md 2.6", "engine/root_cause.py",
                        "IMPLEMENTED"),
    "relationship_analysis": ("metric_dependency_graph.md", "engine/root_cause.py",
                              "IMPLEMENTED"),
    "pattern_discovery": ("business_insight_framework.md Part B", "engine/insight_engine.py",
                          "IMPLEMENTED"),
    "statistical_summary": ("analytics_execution_spec.md 2.5", "engine/change_detection.py",
                            "NOT_IMPLEMENTED"),
    # Method chosen by rolling-origin backtest over the operating era, not by
    # sophistication: damped Holt beat naive at every horizon tested.
    "revenue_forecast": ("analytics_execution_spec.md 2.5 (method selected by "
                         "out-of-sample backtest)", "engine/forecasting.py",
                         "IMPLEMENTED"),
    "forecast_scenario": ("analytics_execution_spec.md 2.5", "engine/forecasting.py",
                          "NOT_IMPLEMENTED"),
    # Descriptive only: counts, typical values, spread, and how measures moved together.
    # Deliberately NOT significance testing -- see the note on statistical_summary.
    "descriptive_analysis": ("analytics_execution_spec.md 2.5", "engine/descriptive.py",
                             "IMPLEMENTED"),
    "kpi_card": ("Phase 6 brief 11", "engine/bi_contract.py", "IMPLEMENTED"),
    "trend_view": ("analytics_execution_spec.md 2.4", "engine/bi_contract.py", "IMPLEMENTED"),
    "period_comparison_view": ("analytics_execution_spec.md 2.3", "engine/bi_contract.py",
                               "IMPLEMENTED"),
    "breakdown_view": ("analytics_execution_spec.md 2.2", "engine/bi_contract.py",
                       "IMPLEMENTED"),
    "filter": ("business_dimensions.md", "engine/dimension_resolver.py", "IMPLEMENTED"),
    "drilldown": ("analytics_execution_spec.md 2.2", "engine/analytics_planner.py",
                  "IMPLEMENTED"),
    "dashboard_narrative": ("answer_contract.md", "engine/answer_renderer.py", "IMPLEMENTED"),
    "metric_definition_surface": ("semantic_metric_registry.csv", "engine/bi_contract.py",
                                  "IMPLEMENTED"),
    "data_quality_indicator": ("data_quality_registry.csv", "engine/bi_contract.py",
                               "IMPLEMENTED"),
    "executive_summary": ("Phase 6 brief 7", "engine/executive_summary.py", "IMPLEMENTED"),
    "management_briefing": ("Phase 6 brief 3", "engine/executive_summary.py", "IMPLEMENTED"),
    "what_changed": ("Phase 6 brief 4", "engine/change_detection.py", "IMPLEMENTED"),
    "attention_required": ("Phase 6 brief 6", "engine/executive_summary.py", "IMPLEMENTED"),
    "pending_decision": ("ai_trust_policy.md 2", "engine/executive_summary.py", "IMPLEMENTED"),
    "investigation_priority": ("insight_generation_spec.md 4", "engine/insight_ranker.py",
                               "IMPLEMENTED"),
    "dq_scan": ("data_quality_report.md", "engine/insight_engine.py", "IMPLEMENTED"),
    "conflict_surface": ("conflicts.md", "engine/insight_engine.py", "IMPLEMENTED"),
    "trust_advisory": ("ai_trust_policy.md", "engine/analyst_intelligence.py", "IMPLEMENTED"),
    "risk_ranking": ("insight_generation_spec.md 4", "engine/insight_ranker.py", "IMPLEMENTED"),
}

# Why a capability is PARTIAL or NOT_IMPLEMENTED. Each cites the specification that declines to
# fix the missing piece -- the gap is the specification's, not this implementation's.
CAP_NOTES = {
    "anomaly_surface": ("analytics_execution_spec.md 2.5 leaves the statistical method to the "
                        "implementation phase; no anomaly threshold exists in the exported "
                        "evidence. " + NOT_DET),
    "trend_break": ("Direction and size of a period change are computed; whether a break is "
                    "material requires a threshold no specification fixes. " + NOT_DET),
    "statistical_summary": ("Descriptive analysis IS available -- counts, typical values, "
                            "spread, and how measures moved together (see "
                            "descriptive_analysis). What is not available is statistical "
                            "INFERENCE: significance tests, p-values and confidence intervals. "
                            "The monthly series repeat themselves almost exactly month to "
                            "month, which leaves 41 months of revenue carrying well under one "
                            "independent observation, so a test would return a number that "
                            "means nothing. " + NOT_DET),
    "descriptive_analysis": ("Descriptive only. It reports what the records look like and how "
                             "measures moved together; it does not test significance and makes "
                             "no causal claim. Correlations are reported on both levels and "
                             "month-to-month changes, because the level figure alone mostly "
                             "records that both measures grew."),
    "forecast_scenario": ("A driver-conditioned forecast ('revenue if occupancy were 80%') "
                          "needs a validated relationship between the driver and revenue. "
                          "Occupancy was tested and rejected: it tracks revenue only because "
                          "both trend upward, and as a predictor it produced roughly seven "
                          "times the error of the univariate model. A monthly occupancy rate "
                          "is not derivable either, because bed records carry no dates. "
                          + NOT_DET),
    "bed_utilization": ("Bed- and apartment-grain occupancy (M.OCC.003/M.OCC.004) carry no "
                        "exported reference and are NOT_DETERMINABLE in the registry. "
                        + NOT_DET),
    "what_changed": ("Change direction is computed; materiality is undefined because "
                     "insight_generation_spec.md 2 condition 3 leaves the threshold to a "
                     "business decision. " + NOT_DET),
    "relationship_analysis": ("Restricted to dependency edges documented in "
                              "metric_dependency_graph.md; no relationship is inferred from "
                              "correlation alone."),
}


def build():
    reg = SemanticRegistry()

    with open(ROLE_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["role_id", "display_name", "defined_by", "origin", "semantic_scope",
                    "domains", "summoning_intents", "capability_ids", "never_does",
                    "reachable_metric_count"])
        for r in ar.ROLES:
            reachable = [m for m in reg.all_ids() if reg.get(m).domain in r.domains]
            origin = ("ai_agent_roles.md 1 (spec-defined lens)"
                      if r.role_id in ar.SPEC_DEFINED_ROLES else
                      "Phase 6 composition of existing machinery (no new domain knowledge)")
            w.writerow([r.role_id, r.display_name, r.source, origin, r.semantic_scope,
                        ";".join(r.domains), ";".join(r.intents), ";".join(r.capabilities),
                        r.never_does, len(reachable)])

    seen = []
    with open(CAP_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["capability_id", "roles", "defined_by", "implemented_in", "status",
                    "limitation"])
        for r in ar.ROLES:
            for c in r.capabilities:
                if c in seen:
                    continue
                seen.append(c)
                spec, impl, status = CAP_IMPL.get(c, ("", "", "NOT_MAPPED"))
                roles = ";".join(x.role_id for x in ar.ROLES if c in x.capabilities)
                w.writerow([c, roles, spec, impl, status, CAP_NOTES.get(c, "")])

    return len(ar.ROLES), len(seen), ar.verify_against_registry(reg)


if __name__ == "__main__":
    n_roles, n_caps, problems = build()
    print(f"roles: {n_roles}  capabilities: {n_caps}")
    print(f"role/registry verification: {problems or '(clean)'}")
    print(f"wrote {ROLE_PATH}")
    print(f"wrote {CAP_PATH}")
    sys.exit(1 if problems else 0)
