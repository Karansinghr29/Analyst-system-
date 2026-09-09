# UI Architecture

The presentation layer for the Phase 1–7 intelligence system.

**The architectural rule that shapes everything (Phase 8 brief 19):** the frontend never
calculates, never queries evidence, never overrides trust, never selects a conflict definition,
never invents a value, never infers causality, never bypasses validation, and never asks an LLM
for a number.

This is enforced structurally rather than by convention. `engine/view_models.py` emits payloads
carrying **rendered values and a render directive** — no formula, no query, no source handle. A
frontend given one of these has nothing to calculate with.

---

## 1. Layers

```
┌─ FRONTEND (React/web — not built) ──────────────────────────────┐
│  renders view models · routes clicks · holds no business logic  │
├─ VIEW MODEL LAYER  engine/view_models.py ───────────────────────┤
│  MetricTile · InsightCard · ChangeCard · OwnerHome              │
│  metric_detail · conflict_view · data_quality_center            │
│  role_workspace · trust_presentation                            │
├─ ENGINE (Phases 1–6, unchanged) ────────────────────────────────┤
│  semantic layer → trust gate → execution → validation →         │
│  reasoning → insights → decision support → answer contract      │
└─────────────────────────────────────────────────────────────────┘
```

The view-model layer is the **only** thing the frontend talks to. It adds no analysis: it
selects a widget from a trust level, formats a value the engine computed, and attaches the
entry points a click can trigger.

---

## 2. Why formatting lives in the view model

A UI that formats numbers is a UI that can round, truncate, or unit-convert a figure away from
what the engine computed. So `format_value()` runs server-side and the payload carries
`display_value` alongside `value`. The validator fails a tile that carries a raw value with no
pre-formatted string, precisely to stop a frontend having to format one itself.

---

## 3. Widget selection is not a design decision

```
SAFE             → kpi_card
DISCLOSE         → kpi_card_with_caveat
SHOW_BOTH        → multi_definition_panel
BLOCK            → conflict_panel_no_headline
NOT_DETERMINABLE → not_determinable_notice
```

Chosen by trust level in code, never by whoever builds a screen. A screen author cannot pick a
KPI card for a BLOCK metric because the payload does not contain a value to put in one.

---

## 4. Data flow for one click

```
owner clicks "Why?" on the Collections tile
  → frontend sends the entry point's `question` + `metric_id`
  → AnalystIntelligence.ask()          [the SAME pipeline as any typed question]
  → view model of the answer returned
  → frontend renders it
```

There is no second analytics path. The dashboard and the chat cannot disagree because they call
the same function.

---

## 5. Registries the frontend builds against

| Registry | Rows | Purpose |
|---|---|---|
| `ui_metric_registry.csv` | 49 | every metric as the UI presents it |
| `dashboard_tile_registry.csv` | 20 | Owner Home tiles |
| `visualization_registry.csv` | 49 | permitted and **forbidden** visuals per metric |
| `role_workspace_registry.csv` | 9 | the workspaces |
| `ai_entrypoint_registry.csv` | 111 | every clickable question |
| `drilldown_registry.csv` | 91 | every drill path and the context it preserves |

All six are **generated** from the live view models, so a registry cannot describe something the
system does not emit.

---

## 6. What is deliberately not built

Live database connectivity, production authentication, a real LLM provider, RAG/vector search,
autonomous agents, external integrations. The presentation layer is proved against the offline
deterministic engine first — which is the point of doing it in this order.
