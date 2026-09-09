"""
validate_phase8_consistency.py -- Phase 8 anti-drift validator.

Checks the 13 required conditions from the Phase 8 brief 21, against the LIVE engine:

   1. every metric exists
   2. every metric trust level matches the live gate
   3. every BLOCK metric has no headline visualization
   4. every SHOW_BOTH metric exposes all required definitions
   5. every NOT_DETERMINABLE metric displays the required unavailable state
   6. every conflict is surfaced where required
   7. every dashboard tile maps to a real metric/insight
   8. every role view maps to the existing role registry
   9. every visualization uses a supported metric
  10. no frontend calculation exists outside the engine
  11. every AI entry point maps to a valid AnalyticsPlan
  12. drilldowns preserve metric/dimension/period context
  13. source CSVs remain byte-identical

Check 10 is the structural one: a UI that can calculate is a UI that can disagree with the
engine. It is enforced by inspecting the view-model payloads for anything a frontend could
compute from -- a formula, a raw query, an unformatted aggregation handle.

Read-only. Modifies nothing.
"""
import csv
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.execution import MetricExecutor
from engine.view_models import ViewModelBuilder, WIDGET_BY_TRUST
from engine.analyst_intelligence import AnalystIntelligence
from engine import analyst_roles, trust_presentation as tp
from engine.result import NOT_DETERMINABLE_TEXT

REGISTRIES = ("ui_metric_registry.csv", "dashboard_tile_registry.csv",
              "visualization_registry.csv", "role_workspace_registry.csv",
              "ai_entrypoint_registry.csv", "drilldown_registry.csv")

DOCS = ("ui_architecture.md", "owner_dashboard_implementation_spec.md",
        "bi_visualization_spec.md", "ai_chat_experience_spec.md", "role_workspace_spec.md",
        "metric_detail_experience_spec.md", "conflict_experience_spec.md",
        "data_quality_center_spec.md", "executive_report_spec.md", "design_system_spec.md",
        "ui_state_model.md", "frontend_engine_contract.md",
        "phase8_implementation_roadmap.md")

BASELINE_SHA = "aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26"

# Keys a view-model payload must NEVER carry: anything a frontend could compute from, or use to
# reach the data directly. Check 10.
FORBIDDEN_PAYLOAD_KEYS = ("sql", "query", "formula", "expression", "connection", "table",
                          "csv_path", "file_path", "raw_rows", "aggregation_fn", "dsl")


def _rows(name):
    p = os.path.join(ROOT, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    registry = SemanticRegistry()
    gate = TrustGate(registry)
    executor = MetricExecutor(registry=registry, gate=gate)
    vb = ViewModelBuilder(registry, gate, executor)
    problems, warnings = [], []

    home = vb.owner_home()
    tiles = home.all_tiles()

    # -- 1, 2, 7: metrics exist, trust matches, tiles map to real metrics --------------------
    for t in tiles:
        if t.metric_id not in registry:
            problems.append(f"[7] dashboard tile {t.metric_id!r} is not a semantic metric")
            continue
        actual = gate.authorize(t.metric_id).effective_level
        if t.trust["trust_level"] != actual:
            problems.append(
                f"[2] tile {t.metric_id}: shows trust {t.trust['trust_level']}, gate says "
                f"{actual}")
        if t.widget != WIDGET_BY_TRUST[actual]:
            problems.append(
                f"[2] tile {t.metric_id}: widget {t.widget} does not match trust {actual}")

    # -- 3: BLOCK has no headline visualization ------------------------------------------------
    for mid in registry.all_ids():
        lvl = gate.authorize(mid).effective_level
        tile = next((t for t in tiles if t.metric_id == mid), None) or vb.tile(mid)
        if lvl == "BLOCK":
            if tile.headline_permitted or tile.value is not None or tile.display_value:
                problems.append(f"[3] {mid} is BLOCK but the tile carries a headline value")
            if tile.chart_type != "none":
                problems.append(f"[3] {mid} is BLOCK but offers chart {tile.chart_type!r}")
        # -- 4: SHOW_BOTH exposes all definitions -----------------------------------------------
        if lvl == "SHOW_BOTH":
            answer = executor.execute(mid)
            if tile.headline_permitted or tile.value is not None:
                problems.append(f"[4] {mid} is SHOW_BOTH but the tile carries a headline")
            if len(tile.definitions) != len(answer.results):
                problems.append(
                    f"[4] {mid}: tile shows {len(tile.definitions)} definition(s) but the "
                    f"engine computed {len(answer.results)}")
        # -- 5: NOT_DETERMINABLE shows the required unavailable state --------------------------
        if lvl == "NOT_DETERMINABLE":
            if tile.value is not None or tile.display_value:
                problems.append(f"[5] {mid} is NOT_DETERMINABLE but the tile shows a value")
            if NOT_DETERMINABLE_TEXT not in (tile.unavailable_reason or ""):
                problems.append(
                    f"[5] {mid}: unavailable state omits the exact required phrase")
            if tile.chart_type != "none":
                problems.append(f"[5] {mid} is NOT_DETERMINABLE but offers a chart")

    # -- 6: every conflict surfaced where required ----------------------------------------------
    conflicted = [m for m in registry.all_ids()
                  if gate.authorize(m).effective_level in ("SHOW_BOTH", "BLOCK")]
    ui_rows = _rows("ui_metric_registry.csv")
    if ui_rows is None:
        problems.append("[6] ui_metric_registry.csv is missing")
    else:
        by_id = {r["metric_id"]: r for r in ui_rows}
        for mid in conflicted:
            row = by_id.get(mid)
            if row is None:
                problems.append(f"[6] conflicted metric {mid} absent from ui_metric_registry")
                continue
            if row["headline_permitted"] != "False":
                problems.append(f"[6] {mid}: UI registry permits a headline")
            if not row["conflict_ids"] and not row["dq_ids"]:
                problems.append(f"[6] {mid}: conflicted but nothing disclosed in the UI registry")
        for mid in conflicted:
            cv = vb.conflict_view(mid)
            if cv["headline_permitted"]:
                problems.append(f"[6] conflict view for {mid} permits a headline")
            if cv["definitions_computable"] and len(cv["definitions"]) < 2:
                problems.append(f"[6] conflict view for {mid} exposes < 2 definitions")
            if not cv["definitions_computable"] and NOT_DETERMINABLE_TEXT not in cv["note"]:
                problems.append(
                    f"[6] conflict view for {mid} has no computable definitions but does not "
                    f"say so with the exact phrase")

    # -- 8: role views map to the role registry --------------------------------------------------
    ws_rows = _rows("role_workspace_registry.csv")
    known_roles = {r.role_id for r in analyst_roles.all_roles()}
    if ws_rows is None:
        problems.append("[8] role_workspace_registry.csv is missing")
    else:
        listed = {r["role_id"] for r in ws_rows}
        for r in listed - known_roles:
            problems.append(f"[8] workspace {r!r} is not a registered analyst role")
        for r in known_roles - listed:
            problems.append(f"[8] role {r!r} has no workspace")
        for row in ws_rows:
            if row["shares_semantic_layer"] != "True" or row["shares_trust_gate"] != "True":
                problems.append(f"[8] workspace {row['role_id']} claims a separate engine")

    # -- 9: visualizations use supported metrics -------------------------------------------------
    viz_rows = _rows("visualization_registry.csv")
    if viz_rows is None:
        problems.append("[9] visualization_registry.csv is missing")
    else:
        for row in viz_rows:
            mid = row["metric_id"]
            if mid not in registry:
                problems.append(f"[9] visualization for unknown metric {mid!r}")
                continue
            lvl = gate.authorize(mid).effective_level
            if row["trust_level"] != lvl:
                problems.append(f"[9] {mid}: visualization trust {row['trust_level']} != {lvl}")
            if row["permitted_widget"] != WIDGET_BY_TRUST[lvl]:
                problems.append(f"[9] {mid}: widget does not match trust {lvl}")
            forbidden = set(f for f in row["forbidden_visuals"].split(";") if f)
            if row["permitted_chart"] in forbidden:
                problems.append(
                    f"[9] {mid}: permitted chart {row['permitted_chart']!r} is also listed as "
                    f"forbidden")
            if lvl in ("BLOCK", "NOT_DETERMINABLE") and row["permitted_chart"] != "none":
                problems.append(f"[9] {mid} is {lvl} but a chart is permitted")

    # -- 10: no frontend calculation ---------------------------------------------------------------
    for t in tiles:
        payload = t.as_dict()
        for key in payload:
            if any(f in key.lower() for f in FORBIDDEN_PAYLOAD_KEYS):
                problems.append(
                    f"[10] tile {t.metric_id} exposes {key!r} -- a frontend given a query or "
                    f"formula can compute, and a UI that can compute can disagree with the "
                    f"engine")
        if t.headline_permitted and t.value is not None and not t.display_value:
            problems.append(
                f"[10] tile {t.metric_id} carries a raw value with no pre-formatted "
                f"display_value, forcing the frontend to format (and so to round) it")

    # -- 11: AI entry points map to a valid plan -----------------------------------------------------
    ep_rows = _rows("ai_entrypoint_registry.csv")
    if ep_rows is None:
        problems.append("[11] ai_entrypoint_registry.csv is missing")
    else:
        ai = AnalystIntelligence(registry=registry)
        seen_questions = {}
        for row in ep_rows:
            q = row["question"]
            if q in seen_questions:
                continue
            a = ai.ask(q)
            ai.reset()
            resolved = (a.owner_intent != "metric_question"
                        or (a.ask_result is not None and a.ask_result.status in
                            ("READY", "BLOCKED", "NEEDS_CLARIFICATION", "NOT_DETERMINABLE",
                             "REJECTED")))
            seen_questions[q] = resolved
            if not resolved:
                problems.append(f"[11] AI entry point {q!r} resolves to no valid plan")
            if row["metric_id"] and row["metric_id"] not in registry:
                problems.append(f"[11] entry point references unknown metric "
                                f"{row['metric_id']!r}")

    # -- 12: drilldowns preserve context ---------------------------------------------------------------
    dd_rows = _rows("drilldown_registry.csv")
    if dd_rows is None:
        problems.append("[12] drilldown_registry.csv is missing")
    else:
        for row in dd_rows:
            if row["metric_id"] not in registry:
                problems.append(f"[12] drilldown for unknown metric {row['metric_id']!r}")
                continue
            for f in ("preserves_metric", "preserves_period", "preserves_dimensions"):
                if row[f] != "True":
                    problems.append(f"[12] drilldown {row['metric_id']} -> "
                                    f"{row['to_surface']} does not preserve {f}")
            if row["trust_gate_applies"] != "True":
                problems.append(
                    f"[12] drilldown {row['metric_id']} -> {row['to_surface']} bypasses the "
                    f"trust gate")
            lvl = gate.authorize(row["metric_id"]).effective_level
            if lvl in ("SHOW_BOTH", "BLOCK") and row["permitted"] == "True" \
                    and row["to_surface"].startswith("breakdown:"):
                problems.append(
                    f"[12] drilldown breaks down conflicted metric {row['metric_id']} into a "
                    f"single series")

    # -- 13: source integrity ---------------------------------------------------------------------------
    manifest = os.path.join(ROOT, "evidence", "file_manifest.csv")
    digest = ""
    with open(manifest, encoding="utf-8-sig") as f:
        src = list(csv.DictReader(f))
    h = hashlib.sha256()
    for r in src:
        p = os.path.join(ROOT, r["file"])
        if not os.path.exists(p):
            problems.append(f"[13] source CSV missing: {r['file']}")
            continue
        with open(p, "rb") as fh:
            h.update(fh.read())
    digest = h.hexdigest()
    if digest != BASELINE_SHA:
        problems.append(f"[13] SOURCE CSVs CHANGED: {digest} != baseline {BASELINE_SHA}")

    # -- documents present -------------------------------------------------------------------------------
    missing_docs = [d for d in DOCS if not os.path.exists(os.path.join(ROOT, d))]
    for d in missing_docs:
        problems.append(f"[docs] {d}: MISSING -- declared as a Phase 8 deliverable")

    print("=" * 88)
    print("PHASE 8 CONSISTENCY VALIDATION -- presentation layer vs. the live engine")
    print("=" * 88)
    print(f"\n[documents]     {len(DOCS) - len(missing_docs)}/{len(DOCS)}")
    print(f"[registries]    {sum(1 for r in REGISTRIES if _rows(r) is not None)}"
          f"/{len(REGISTRIES)}")
    print(f"[tiles]         {len(tiles)} "
          f"({sum(1 for t in tiles if not t.headline_permitted)} headline-forbidden)")
    print(f"[metrics]       {len(registry.all_ids())}")
    print(f"[conflicts]     {len(conflicted)} conflicted metrics, all disclosure-checked")
    print(f"[entry points]  {len(ep_rows or [])}")
    print(f"[drill paths]   {len(dd_rows or [])}")
    print(f"[source]        SHA-256 {digest[:16]}... "
          f"{'MATCHES baseline' if digest == BASELINE_SHA else 'CHANGED'}")

    print(f"\n[problems]      {len(problems)}")
    print(f"[warnings]      {len(warnings)}")
    if problems:
        print("\nINCONSISTENCIES:")
        for p in problems:
            print(f"   {p}")
    else:
        print("\nNo inconsistency between the presentation layer and the engine.")
    for w in warnings:
        print(f"   warning: {w}")

    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
