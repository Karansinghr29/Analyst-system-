"""
build_phase9_contracts.py -- Phase 9 (W6). Generates the client-facing export contracts.

Generated from the LIVE service and registries, so a contract cannot describe an endpoint the
service does not serve or a measure the semantic layer does not define.

Produces:
    openapi.json                    -- the API schema, from the running FastAPI app
    powerbi_dataset_descriptor.json -- a Power BI dataset the semantic layer can actually back
    api_endpoint_registry.csv       -- every endpoint, with what it serves and its trust rules
"""
import csv
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from api.service import AnalyticsService, create_app

OPENAPI_PATH = os.path.join(ROOT, "openapi.json")
POWERBI_PATH = os.path.join(ROOT, "powerbi_dataset_descriptor.json")
ENDPOINTS_PATH = os.path.join(ROOT, "api_endpoint_registry.csv")

NOT_DET = "Not determinable from exported evidence."

# What each endpoint serves, and the trust rule that governs its payload. Recorded so a client
# implementer sees the constraint next to the route rather than in a separate document.
ENDPOINT_NOTES = {
    "/health": ("system", "Reports the data source status and whether re-validation passed."),
    "/api/trust": ("trust", "Trust posture for all 49 metrics."),
    "/api/llm/adapters": ("system",
                          "Adapter shapes. A credential in the environment does NOT enable one."),
    "/api/owner/home": ("dashboard",
                        "BLOCK/SHOW_BOTH tiles carry no value field -- the refusal is an "
                        "absence, not a flag a client may ignore."),
    "/api/metrics": ("dashboard",
                     "Authorization filters WHICH metrics are listed, never how they are gated."),
    "/api/metrics/{metric_id}": ("detail", "Full metric detail with evidence and validation."),
    "/api/metrics/{metric_id}/conflict": (
        "conflict", "Every competing definition. Never a winner, never a default."),
    "/api/insights": ("insights", "Ranked feed; conflicted insights carry no headline."),
    "/api/changes": ("changes", "Direction and size only; materiality is undefined."),
    "/api/data-quality": ("dq", "The DQ register by recorded severity."),
    "/api/roles": ("roles", "Role registry with per-role boundaries."),
    "/api/roles/{role_id}/workspace": ("roles", "Same metrics, same trust; only the lens differs."),
    "/api/report/executive": ("report", "Generated from engine output; no separate KPI maths."),
    "/api/ask": ("conversation",
                 "Natural language through the same pipeline. LLM output is guarded and "
                 "discardable."),
    "/api/conversations/{conversation_id}": (
        "conversation", "History plus persisted clarification and selection state."),
}


def build_openapi():
    app = create_app(AnalyticsService(db_path=os.path.join(tempfile.mkdtemp(), "contract.db")))
    schema = app.openapi()
    with open(OPENAPI_PATH, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    return schema


def build_endpoint_registry(schema):
    rows = []
    for path, ops in sorted(schema.get("paths", {}).items()):
        for method, op in sorted(ops.items()):
            surface, note = ENDPOINT_NOTES.get(path, ("", ""))
            rows.append({
                "path": path,
                "method": method.upper(),
                "operation_id": op.get("operationId", ""),
                "surface": surface,
                "accepts_free_form_query": False,
                "accepts_formula": False,
                "serves_engine_payload": True,
                "trust_rule": note,
            })
    with open(ENDPOINTS_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows


def build_powerbi_descriptor():
    """A Power BI dataset the semantic layer can actually back.

    The three anti-idioms from `powerbi_analytics_mapping.md` are encoded as data, not prose:
      * a conflicted measure is NOT a measure -- it is a multi-value table
      * there is no single conformed date table -- the date basis is per metric
      * blank is not zero -- a NOT_DETERMINABLE measure renders text, never a value
    """
    registry = SemanticRegistry()
    gate = TrustGate(registry)

    measures, conflict_tables, unavailable = [], [], []
    for mid in registry.all_ids():
        spec = registry.get(mid)
        lvl = gate.authorize(mid).effective_level
        common = {
            "metric_id": mid,
            "name": spec.display_name or spec.semantic_name,
            "description": spec.definition[:400],
            "domain": spec.domain,
            "trust_level": lvl,
            "date_basis": spec.date_field[:160],
            "conflict_ids": list(spec.conflict_ids),
            "dq_ids": list(spec.dq_ids),
        }
        if lvl in ("SAFE", "DISCLOSE"):
            measures.append({**common, "render": "measure",
                             "caveat_required": lvl == "DISCLOSE"})
        elif lvl in ("SHOW_BOTH", "BLOCK"):
            conflict_tables.append({
                **common, "render": "multi_value_table",
                "single_measure_forbidden": True,
                "reason": ("Competing evidence-backed definitions exist. Authoring this as a "
                           "single DAX measure would silently pick one."),
                "chart_permitted": lvl == "SHOW_BOTH",
            })
        else:
            unavailable.append({**common, "render": "text_notice",
                                "text": NOT_DET,
                                "blank_is_not_zero": True})

    descriptor = {
        "dataset": "AI Business Analytics",
        "source_of_truth": "semantic_metric_registry.csv (49 metrics)",
        "authoring_rule": ("No measure may be authored in the BI tool. If it is not in the "
                           "49-metric registry, it is not a measure."),
        "measures": measures,
        "conflict_tables": conflict_tables,
        "unavailable_measures": unavailable,
        "date_tables": sorted({m["date_basis"].split("(")[0].strip()
                               for m in measures if m["date_basis"]}),
        "date_table_rule": ("One date table per date basis, joined per metric as the registry "
                            "documents. A single conformed calendar would silently re-date "
                            "metrics onto a field their definition does not use."),
        "forbidden_measures": [
            {"name": "Profit = Revenue - Expenses",
             "reason": "This is M.PROFIT.001, which is BLOCK."},
            {"name": "Occupancy %",
             "reason": "Five definitions differ on both numerator and denominator."},
            {"name": "Collection Efficiency",
             "reason": "No such metric exists; structurally absent."},
            {"name": "Any YoY over maintenance or EB",
             "reason": "20 months and 1-5 months of coverage."},
            {"name": "Any threshold-coloured KPI",
             "reason": "No materiality threshold exists in the evidence."},
        ],
        "counts": {"measures": len(measures), "conflict_tables": len(conflict_tables),
                   "unavailable": len(unavailable), "total": len(registry.all_ids())},
    }
    with open(POWERBI_PATH, "w", encoding="utf-8") as f:
        json.dump(descriptor, f, indent=2, ensure_ascii=False)
    return descriptor


def main():
    schema = build_openapi()
    endpoints = build_endpoint_registry(schema)
    pbi = build_powerbi_descriptor()

    print(f"openapi.json                     {len(schema.get('paths', {}))} paths")
    print(f"api_endpoint_registry.csv        {len(endpoints)} operations")
    print(f"powerbi_dataset_descriptor.json  {pbi['counts']['measures']} measures, "
          f"{pbi['counts']['conflict_tables']} conflict tables, "
          f"{pbi['counts']['unavailable']} unavailable "
          f"(of {pbi['counts']['total']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
