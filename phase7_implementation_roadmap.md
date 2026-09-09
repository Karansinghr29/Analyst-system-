# Phase 7 Implementation Roadmap

What remains to be built, in an order that never ships a capability ahead of the safeguard that
constrains it. The same governing rule as `implementation_roadmap.md`, carried forward.

**Phase 7 itself is a blueprint.** Nothing below Phase 8 is built. The order below is not a
preference — each phase's exit criteria are the next phase's entry criteria, and reordering would
mean re-deriving a guarantee the skipped phase provides.

---

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Analytics Engine | complete — 46/49 metrics, 80 checks |
| 2 | Trust & Validation | complete — 49/49, clean propagation audit |
| 3 | Question Understanding + Planning | complete — 48/48 plans |
| 4 | LLM Interface | complete — 34/34, 11/11 criteria |
| 5 | Insights + Conversation | complete — 31/31 scenarios |
| 6 | Analyst Intelligence | complete — 34 scenarios, 0 failures |
| **7** | **Product blueprint** | **this phase — 13 documents, 3 registries, consistency-validated** |
| 8 | Presentation layer | not started |
| 9 | Live data | not started |
| 10 | Production | not started |

---

## Phase 8 — Presentation Layer

**Builds:** the Owner Dashboard, conversation surface, and BI views, against the registries this
phase generated.

**Entry:** Phase 7 consistency validation passes.

**Exit:**
- Every tile honours `owner_dashboard_registry.csv`'s `render_directive`. Specifically: the
  three tiles with `headline_permitted = false` render no single figure.
- `validate_card()` passes for every rendered card, in CI.
- All five click paths work, carrying context per the integration spec.
- The dashboard is complete and correct **with the LLM disabled** — verbalization is an
  enhancement, never a dependency.
- A NOT_DETERMINABLE metric renders the exact sentence, with no chart and no zero.

**Explicitly deferred:** live data, authentication, a real LLM provider.

**The risk this phase carries:** a BI surface is where the "one number per tile" idiom is
strongest. The registries exist precisely so that resisting it is a check rather than a habit.

---

## Phase 9 — Live Data

**Builds:** the live connector replacing the manifest ingestion layer — and *only* that layer.

**Entry:** Phase 8 complete.

**Exit — the unconditional requirement from `implementation_roadmap.md`:**

> "every trust rule, conflict, and DQ finding documented in this project must be **re-verified
> against live data before being trusted to still hold** — a conflict resolved in the live system
> must trigger an update to `semantic_metric_registry.csv`'s trust level, never a silent
> divergence."

Concretely:
1. All 80 validation checks re-run against live data; every difference explained.
2. All 24 conflicts re-tested. One that no longer reproduces triggers a **registry trust-level
   update with a recorded owner decision** — never a quiet downgrade.
3. All 32 DQ findings re-counted.
4. Snapshot-date semantics re-derived, not carried forward: the fixed `2026-08-29` is a property
   of the export, not of the business.
5. **Read-only.** No live database modification.

**This is a re-validation phase with a connectivity step in it, not a connectivity phase.**
Treating it as plumbing is the single most likely way to lose the guarantees built so far.

---

## Phase 10 — Production

**Builds:** real LLM provider, authentication, deployment, monitoring.

**Entry:** Phase 9 complete.

**Exit:**
- The provider swap changes nothing below the LLM boundary — proven by re-running the full suite
  against the live provider and getting identical trust postures, metric sets, and values.
- Verbalization guard violations are monitored: a rising rate is a model-quality signal.
- Authentication does not create per-user trust levels. Trust is a property of the evidence, not
  of the viewer.

---

## Standing constraints (all phases)

| Constraint | Enforcement |
|---|---|
| Source CSVs immutable | SHA-256 baseline checked by the consistency validator |
| No invented metric | The 49-metric registry is the only source |
| No silent conflict resolution | `conflict_disclosure_registry.csv` + gate |
| BLOCK means no headline | Gate + card contract + verbalization guard |
| SHOW_BOTH stays visible | Same |
| NOT_DETERMINABLE stays exact | The sentence "Not determinable from exported evidence." checked across every surface |
| No invented threshold | Materiality and anomaly report as undefined |
| No causal claim | Hedge-language requirement + guard |
| LLM stays untrusted | Contract has no channel for a value or a verdict |
| No autonomous agent bypassing the engine | Any agent must call `AnalystIntelligence.ask()` |

---

## What would change this roadmap

Stated so the plan can be falsified rather than merely followed:

- **An owner decision resolving a conflict** — that metric's trust level changes in the registry,
  and every surface follows automatically. Phase 8 does not need rework.
- **A materiality threshold being set by the business** — change detection gains a materiality
  classification. It would then be a *business* threshold, recorded as such, not an invented one.
- **Live data contradicting a documented conflict** — Phase 9's re-verification catches it and
  the registry is updated with the decision recorded.
- **A real LLM proving materially better at phrase coverage** — the deterministic matcher becomes
  a fallback rather than the primary path. Nothing below the boundary changes.
