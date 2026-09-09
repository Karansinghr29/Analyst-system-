"""
build_phase8_registries.py -- generates the Phase 8 UI registries FROM the live view models.

Generated, not authored: a registry row is produced by actually building the view model, so it
cannot describe a tile, chart, workspace, entry point, or drill path the system does not emit.
That is what makes the Phase 8 anti-drift validator meaningful rather than circular.

Produces:
    ui_metric_registry.csv        -- every metric, as the UI will present it
    dashboard_tile_registry.csv   -- every Owner Home tile
    visualization_registry.csv    -- which visual each metric supports, and which it must not
    role_workspace_registry.csv   -- the 9 workspaces
    ai_entrypoint_registry.csv    -- every clickable question in the UI
    drilldown_registry.csv        -- every drill path, with the context it preserves
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
from engine.view_models import (ViewModelBuilder, WIDGET_BY_TRUST, CHART_NONE, CHART_LINE,
                                CHART_MULTI_DEF_BAR)
from engine import analyst_roles, trust_presentation as tp

NOT_DET = "Not determinable from exported evidence."

PATHS = {
    "ui_metric": os.path.join(ROOT, "ui_metric_registry.csv"),
    "tiles": os.path.join(ROOT, "dashboard_tile_registry.csv"),
    "viz": os.path.join(ROOT, "visualization_registry.csv"),
    "workspaces": os.path.join(ROOT, "role_workspace_registry.csv"),
    "entrypoints": os.path.join(ROOT, "ai_entrypoint_registry.csv"),
    "drilldown": os.path.join(ROOT, "drilldown_registry.csv"),
}

# Visuals that are FORBIDDEN at each trust level. Expressed as prohibitions rather than
# permissions, because the failure mode is a UI rendering something it was never told not to.
FORBIDDEN_VISUALS = {
    "SAFE": (),
    "DISCLOSE": (),
    "SHOW_BOTH": ("kpi_card", "single_value", "line", "gauge", "sparkline"),
    "BLOCK": ("kpi_card", "single_value", "line", "bar", "gauge", "sparkline",
              "multi_definition_bar"),
    "NOT_DETERMINABLE": ("kpi_card", "single_value", "line", "bar", "gauge", "sparkline",
                         "zero_placeholder"),
}


def write(path, rows):
    if not rows:
        return 0
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main():
    registry = SemanticRegistry()
    gate = TrustGate(registry)
    executor = MetricExecutor(registry=registry, gate=gate)
    vb = ViewModelBuilder(registry, gate, executor)

    home = vb.owner_home()
    tiles_by_id = {t.metric_id: t for t in home.all_tiles()}

    # --- ui_metric_registry -------------------------------------------------------------------
    ui_rows = []
    for mid in registry.all_ids():
        spec = registry.get(mid)
        tile = tiles_by_id.get(mid) or vb.tile(mid)
        pres = tp.present(tile.trust["trust_level"])
        ui_rows.append({
            "metric_id": mid,
            "display_name": tile.title,
            "domain": spec.domain,
            "trust_level": pres.trust_level,
            "owner_label": pres.owner_label,
            "badge": pres.badge,
            "tone": pres.tone,
            "headline_permitted": tile.headline_permitted,
            "widget": tile.widget,
            "chart_type": tile.chart_type,
            "definition_count": len(tile.definitions),
            "has_caveat": bool(tile.caveat),
            "conflict_ids": ";".join(tile.conflict_ids),
            "dq_ids": ";".join(tile.dq_ids),
            "validation_status": tile.validation_status,
            "drilldown_dimensions": ";".join(tile.drilldown_dimensions),
            "evidence_count": len(tile.evidence),
        })

    # --- dashboard_tile_registry --------------------------------------------------------------
    tile_rows = []
    for t in home.all_tiles():
        tile_rows.append({
            "section": t.section,
            "metric_id": t.metric_id,
            "title": t.title,
            "widget": t.widget,
            "headline_permitted": t.headline_permitted,
            "display_value": t.display_value,
            "definition_count": len(t.definitions),
            "owner_label": t.trust["owner_label"],
            "trust_level": t.trust["trust_level"],
            "chart_type": t.chart_type,
            "caveat_rendered": bool(t.caveat),
            "conflict_ids": ";".join(t.conflict_ids),
            "ai_entry_points": ";".join(e["action"] for e in t.ai_entry_points),
            "unavailable_reason": t.unavailable_reason[:160],
        })

    # --- visualization_registry ----------------------------------------------------------------
    viz_rows = []
    for mid in registry.all_ids():
        tile = tiles_by_id.get(mid) or vb.tile(mid)
        lvl = tile.trust["trust_level"]
        viz_rows.append({
            "metric_id": mid,
            "trust_level": lvl,
            "permitted_widget": WIDGET_BY_TRUST[lvl],
            "permitted_chart": tile.chart_type,
            "forbidden_visuals": ";".join(FORBIDDEN_VISUALS[lvl]),
            "series_available": tile.chart_type in (CHART_LINE,),
            "reason_no_chart": ("" if tile.chart_type != CHART_NONE else
                                ("competing definitions -- a single series would pick one"
                                 if lvl in ("SHOW_BOTH", "BLOCK") else
                                 f"no exported reference exists. {NOT_DET}"
                                 if lvl == "NOT_DETERMINABLE" else
                                 "no month-keyed series exists for this metric")),
        })

    # --- role_workspace_registry ----------------------------------------------------------------
    ws_rows = []
    for role in analyst_roles.all_roles():
        ws = vb.role_workspace(role.role_id)
        conflicted = sum(1 for t in ws["tiles"] if not t["headline_permitted"])
        ws_rows.append({
            "role_id": role.role_id,
            "display_name": role.display_name,
            "focus": role.semantic_scope,
            "domains": ";".join(role.domains),
            "metric_count": ws["metric_count"],
            "conflicted_tiles": conflicted,
            "capabilities": ";".join(role.capabilities),
            "never_does": role.never_does,
            "shares_semantic_layer": True,
            "shares_trust_gate": True,
        })

    # --- ai_entrypoint_registry -----------------------------------------------------------------
    ep_rows = []
    for e in home.ai_entry_points:
        ep_rows.append({"surface": "owner_home", "object_id": "home", "action": e["action"],
                        "label": e["label"], "question": e["question"], "metric_id": ""})
    for t in home.all_tiles():
        for e in t.ai_entry_points:
            ep_rows.append({"surface": "tile", "object_id": t.metric_id,
                            "action": e["action"], "label": e["label"],
                            "question": e["question"], "metric_id": e.get("metric_id", "")})
    for i in home.insights:
        for e in i.ai_entry_points:
            ep_rows.append({"surface": "insight", "object_id": i.insight_id,
                            "action": e["action"], "label": e["label"],
                            "question": e["question"], "metric_id": ""})
    for c in home.changes:
        for e in c.ai_entry_points:
            ep_rows.append({"surface": "change", "object_id": c.metric_id,
                            "action": e["action"], "label": e["label"],
                            "question": e["question"], "metric_id": e.get("metric_id", "")})

    # --- drilldown_registry ----------------------------------------------------------------------
    dd_rows = []
    for t in home.all_tiles():
        lvl = t.trust["trust_level"]
        dd_rows.append({
            "from_surface": "owner_home",
            "metric_id": t.metric_id,
            "to_surface": "metric_detail",
            "permitted": True,
            "preserves_metric": True, "preserves_period": True, "preserves_dimensions": True,
            "trust_gate_applies": True,
            "next_levels": "trend;breakdown;detail;evidence" if t.headline_permitted
                           else "definitions;evidence",
            "blocked_reason": ("" if t.headline_permitted else
                               "competing definitions -- drill path leads to the definitions "
                               "panel, never to a single series"),
        })
        for dim in t.drilldown_dimensions:
            dd_rows.append({
                "from_surface": "metric_detail",
                "metric_id": t.metric_id,
                "to_surface": f"breakdown:{dim}",
                "permitted": t.headline_permitted,
                "preserves_metric": True, "preserves_period": True,
                "preserves_dimensions": True, "trust_gate_applies": True,
                "next_levels": "detail;evidence",
                "blocked_reason": ("" if t.headline_permitted else
                                   "a conflicted metric has no single series to break down"),
            })

    counts = {
        "ui_metric": write(PATHS["ui_metric"], ui_rows),
        "tiles": write(PATHS["tiles"], tile_rows),
        "viz": write(PATHS["viz"], viz_rows),
        "workspaces": write(PATHS["workspaces"], ws_rows),
        "entrypoints": write(PATHS["entrypoints"], ep_rows),
        "drilldown": write(PATHS["drilldown"], dd_rows),
    }
    for name, n in counts.items():
        print(f"{os.path.basename(PATHS[name]):32s} {n} rows")
    blocked = sum(1 for r in tile_rows if not r["headline_permitted"])
    print(f"\n{blocked} of {len(tile_rows)} dashboard tiles may NOT render a headline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
