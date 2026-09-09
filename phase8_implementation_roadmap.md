# Phase 8 Implementation Roadmap

What Phase 8 delivered, and what a frontend build would still need.

---

## 1. Delivered in Phase 8

| Layer | Artifact |
|---|---|
| Trust presentation | `engine/trust_presentation.py` — 5 states, owner labels, 6 insight categories |
| View models | `engine/view_models.py` — tiles, insights, changes, owner home, metric detail, conflict view, DQ center, role workspaces |
| Registries (generated) | 6 CSVs: ui metric, dashboard tile, visualization, role workspace, AI entry point, drilldown |
| Specifications | 13 documents |
| Anti-drift validator | `scripts/validate_phase8_consistency.py` — 13 checks |
| Tests | `tests/test_phase8_*.py` |

**Not delivered, by design:** the frontend itself. Phase 8 proves the presentation *contract*
against the offline engine first, so that a UI build has a validated target rather than a moving
one.

---

## 2. What a frontend build receives

1. Six registries describing every tile, visual, workspace, entry point and drill path — all
   generated, so none can describe something the system does not emit.
2. `ViewModelBuilder` producing complete render payloads.
3. A validator that fails CI on drift.
4. Thirteen specifications covering layout, interaction, trust language, and state.

A frontend implementer needs no business decisions. Every one has been made and recorded.

---

## 3. Phase 9 — Frontend implementation

**Entry:** Phase 8 validator passes; full regression green.

**Exit:**
- Every tile renders per its registry `widget` and `render_directive`.
- The three headline-forbidden tiles render no single figure, at every breakpoint including
  mobile.
- The six terminal states are visually distinct — verified by inspection, not assumed.
- Every AI entry point routes to `AnalystIntelligence.ask()`; no second analytics path exists.
- Trust survives every drilldown level.
- The dashboard is complete with the LLM disabled.
- Accessibility: trust never conveyed by colour alone; conflict panels keyboard-navigable.

**The risk this phase carries:** a dashboard framework will make the one-number-per-tile pattern
the path of least resistance. The registries exist so that resisting it is a check rather than a
habit.

---

## 4. Phase 10 — Live data

Unchanged from `phase7_implementation_roadmap.md`: the live connector replaces only the ingestion
layer, and **every trust rule, conflict and DQ finding must be re-verified against live data
before being trusted to still hold.** A conflict that no longer reproduces triggers a registry
trust-level update with a recorded owner decision — never a silent divergence.

Read-only. No live database modification.

---

## 5. Phase 11 — Production

Real LLM provider · authentication · deployment · monitoring.

Two constraints carry forward: a provider swap must change nothing below the LLM boundary, and
authentication must not create per-user trust levels — trust is a property of the evidence, not
of the viewer.

---

## 6. Standing constraints

| Constraint | Enforced by |
|---|---|
| Source CSVs immutable | SHA-256 baseline, validator check 13 |
| No frontend calculation | Payload inspection, check 10 |
| BLOCK renders no headline | Check 3 + absent `value` field |
| SHOW_BOTH shows all definitions | Check 4 |
| NOT_DETERMINABLE shows the exact phrase | Check 5 |
| Conflicts surfaced everywhere | Check 6 |
| Drilldowns preserve context and the gate | Check 12 |
| Entry points resolve to real plans | Check 11 |

---

## 7. Known gaps carried into Phase 9

- **`M.OCC.005`** — conflict real, figures not computable; renders the conflict without numbers.
- **Opportunity category empty** — no evidence supports an opportunity trigger. Honest, not a bug.
- **Anomaly and materiality unavailable** — no thresholds exist in any specification.
- **3 of 49 metrics have charts** — the rest have no month-keyed series.
- **20 metrics unvalidated** — no exported reference existed; reported UNVERIFIED, never MATCH.
- **Currency formatting emits `₹`** — payloads are UTF-8; a consuming surface must not be
  latin-1.
