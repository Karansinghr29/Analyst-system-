# Implementation Roadmap

Sequences the build-out of everything specified in the 9 architecture documents into 6 phases.
**This document does not perform any implementation work** — it defines scope, entry/exit
criteria, and dependencies for each phase, so that implementation (a future, separate effort)
proceeds in an order that never violates a trust rule by building a user-facing capability ahead
of the safeguard that constrains it.

**Governing rule for every phase:** no phase may ship a capability that lets a number reach a
user before the trust/validation/evidence machinery that governs it exists. This inverts the
"build the exciting part first" instinct deliberately — Phase 1 is trust-and-evidence
infrastructure, and the natural-language interface (what a stakeholder actually sees) is Phase 4,
not Phase 1.

---

## Phase 1 — Analytics Engine

**Builds:** The Execution layer (`analytics_execution_spec.md`) — evidence loading (extending
the manifest-driven discipline already proven in `scripts/validation/common.py`), filter/
aggregation/grain application exactly per `semantic_metric_registry.csv`, grouping, period
comparison mechanics.

**Entry criteria:** Semantic layer complete (already true — this is the immediate next phase).

**Exit criteria:** For every one of the 43 metrics with a `validation_reference`, the Execution
Engine reproduces the exact value already recorded in `validation_summary.csv`, live, on demand
— i.e. Phase 1's own acceptance test is "pass `ai_evaluation_framework.md` §1.1 in full." No
trend/anomaly/driver logic yet — single-value and grouped lookups only.

**Explicitly deferred to a later phase:** trust enforcement (a Phase 1 build may compute a BLOCK
metric's value internally for testing, but must not expose it un-gated — Phase 2 adds the gate),
natural-language input (Phase 1 is queried via resolved `metric_id` + parameters directly, not
free text).

---

## Phase 2 — Trust & Validation

**Builds:** The Trust & Conflict Gate (Layer 3 of `ai_analytics_architecture.md`), the Validator
role (`ai_agent_roles.md`), and the Validation stage (`analytics_execution_spec.md` §8) —
enforcing `semantic_metric_registry.csv.trust_level` and `metric_dependency_graph.md` §6's
propagation table as a hard gate in front of every Phase 1 execution path.

**Entry criteria:** Phase 1 complete and passing its exit criteria.

**Exit criteria:** Every one of the 49 metrics, queried through the now-gated path, returns the
correct trust posture — pass `ai_evaluation_framework.md` §1.2 and §1.3 in full (all BLOCK
metrics refuse a single number under every phrasing variant tested; all SHOW_BOTH metrics return
the full definition set; propagation correctly downgrades dependents and correctly does NOT
downgrade the documented non-dependencies). This phase also implements the Answer Contract's
structural fields (`answer_contract.md`) — evidence citation, calculation provenance, confidence
model — since these are inseparable from a trustworthy gated answer.

**Explicitly deferred:** business reasoning beyond CALCULATION (no trends/drivers/hypotheses
yet), natural-language input.

---

## Phase 3 — Business Reasoning

**Builds:** The Business Reasoner role — the FACT→CALCULATION→OBSERVATION→INFERENCE→HYPOTHESIS→
RECOMMENDATION ladder (`business_reasoning_spec.md`), trend/anomaly/driver Analytics Plans
(`analytics_execution_spec.md` §2.4–2.6), and the epistemic-labelling requirements of
`answer_contract.md`.

**Entry criteria:** Phase 2 complete — reasoning must never operate on an ungated number.

**Exit criteria:** Pass `ai_evaluation_framework.md` §1.6 (epistemic-ladder compliance) and the
driver-analysis worked example in `business_reasoning_spec.md` §4 reproduces correctly end-to-end
(including correctly checking `data_quality_report.md` before reporting an anomaly as a business
signal — the owner-rent single-batch-posting scenario is the canonical test case). This phase
also implements the historical-coverage/YoY guards (`question_understanding_spec.md` §5.3) since
trend generation is where they bite.

**Explicitly deferred:** natural-language question parsing (reasoning is still invoked with
resolved parameters, not free text), proactive insight generation (Phase 5).

---

## Phase 4 — AI Question Interface

**Builds:** Question Understanding (`question_understanding_spec.md`) — intent classification,
metric resolution (including the mandatory family-resolution rule), dimension resolution, time
resolution, and ambiguity/clarification handling. **This is the first phase where natural
language enters the system.**

**Entry criteria:** Phases 1–3 complete — the interface's job is purely to resolve a question
into the parameters the already-built, already-gated, already-reasoning-capable pipeline
consumes; it must not be built before that pipeline exists, or ambiguity/trust handling would
have to be retrofitted rather than enforced by construction.

**Exit criteria:** Pass `ai_evaluation_framework.md` §3's full 10-scenario suite end-to-end, plus
§1.4's hallucination/evidence-grounding tests (no-metric, no-dimension, citation-completeness,
created_at-substitution). This is the phase where `question_understanding_spec.md` §6.1's worked
examples ("which property is best," "what's our profit," etc.) must all resolve correctly.

**Note on scope:** this phase explicitly does not include LLM API selection, prompt engineering,
or a chat UI — those are downstream of this architecture (per the task brief's own exclusions)
and belong to whatever product-engineering effort consumes this specification. Phase 4's
deliverable is the *resolution logic* a chat interface would call into, not the chat interface
itself.

---

## Phase 5 — Insight/Alert System

**Builds:** The Insight Generator role — triggers, candidate generation, ranking, and delivery
(`insight_generation_spec.md`).

**Entry criteria:** Phases 1–4 complete — proactive insights reuse the exact same
Execution/Trust/Reasoning/Answer-Contract machinery as reactive answers; building this before
that machinery exists would mean re-deriving trust/evidence handling twice.

**Exit criteria:** The worked example in `insight_generation_spec.md` §7 (phantom-deposit
proactive surfacing) reproduces correctly, and all four trigger categories (§2) fire correctly
against the current evidence state — specifically, confirm the 4 CRITICAL and 8 HIGH DQ findings
from `data_quality_report.md` are all standing candidates ranked above LOW/INFORMATIONAL
findings per §4's priority ordering.

---

## Phase 6 — Production

**Builds:** Everything outside this specification's scope by design — LLM integration, chat UI,
backend services, live database connectivity (replacing or supplementing the static evidence
layer), deployment, authentication, monitoring, and the concrete test-automation tooling that
operationalizes `ai_evaluation_framework.md`.

**Entry criteria:** Phases 1–5 complete and passing their respective evaluation criteria in full.

**Exit criteria:** Not specified here — production readiness criteria (uptime, latency, security
review, live-data reconciliation against the original static evidence package) are a separate
effort's responsibility, informed by but not fixed by this document. **One requirement carries
forward unconditionally into Phase 6, however:** if/when the system moves from the static
exported evidence to a live database connection, every trust rule, conflict, and DQ finding
documented in this project must be **re-verified against live data before being trusted to still
hold** — a conflict resolved in the live system (e.g. `tenant_transactions` deprecated, or the
`v_occupancy` SQL defect fixed) must trigger an update to `semantic_metric_registry.csv`'s trust
level, never a silent divergence between what this specification says and what production
actually does.

---

## Cross-phase dependency summary

```
Phase 1 (Analytics Engine)
   |
   v
Phase 2 (Trust & Validation)  <-- gates every later phase's user-facing output
   |
   v
Phase 3 (Business Reasoning)
   |
   v
Phase 4 (AI Question Interface)  <-- first phase with natural-language input
   |
   v
Phase 5 (Insight/Alert System)  <-- reuses Phases 1-4 machinery, adds proactive triggers
   |
   v
Phase 6 (Production)  <-- everything explicitly out of scope for this architecture phase
```

No phase may be reordered ahead of a phase it depends on without re-deriving the guarantees the
skipped phase would otherwise have provided — in particular, **Phase 4 must never be built
before Phase 2**, since a natural-language interface built directly on top of an ungated
Analytics Engine is exactly the failure mode (a BLOCK metric reaching a user as a confident
single number) this entire project exists to prevent.
