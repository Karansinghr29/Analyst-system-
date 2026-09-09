# AI Agent Roles

Defines the **functional roles** that together compose the AI Business Analyst persona, and how
each role's responsibility maps to the architecture layers already specified. **This is a role
and responsibility specification, not agent code, not an orchestration framework, not a
multi-agent implementation.** "Roles" here means a clean separation of concerns that a later
implementation phase may realize as separate components, separate prompts, or a single unified
process — this document does not mandate a particular implementation topology, only the
boundaries of responsibility that must exist somewhere in whatever topology is eventually built.

---

## 1. The composed persona

The brief asks for a system that behaves as a combination of Data Analyst, Data Scientist, BI
Analyst, Business Analyst, Financial Analyst, and Operations Analyst. These are **not** six
separate functional roles to implement — they are six **domain lenses** the same underlying
functional pipeline (§2) must be able to apply, because each lens draws on a different slice of
the same semantic layer:

| Persona lens | Primary semantic-layer areas it draws on | Primarily engages |
|---|---|---|
| **Data Analyst** | Any metric — raw lookups, filters, groupings | Question Understanding, Analytics Execution |
| **Data Scientist** | Trend/anomaly/driver analysis across any domain | Analytics Execution (trend/anomaly/driver plans), Business Reasoning |
| **BI Analyst** | Cross-domain dashboards, KPI composition | Analytics Execution (grouped/comparison plans), Answer Assembly |
| **Business Analyst** | Cross-cutting synthesis, risk scans, recommendations | Business Reasoning (full ladder), Insight Generation |
| **Financial Analyst** | `semantic_layer.md` §1–6, §10–16 (revenue, collections, invoices, AR, deposits, expenses, owner payments, profit, ledger, cash) | All layers, financial domain |
| **Operations Analyst** | `semantic_layer.md` §7–9, §13–14 (occupancy, tenants, lifecycle, maintenance, EB) | All layers, operations domain |

A single question may require multiple lenses simultaneously (e.g. "why did profit fall" is
Financial Analyst + Data Scientist for the driver decomposition). The functional roles in §2 are
what actually do the work; the lenses above describe **which domain knowledge** (already fully
catalogued in `semantic_layer.md`/`business_dimensions.md`) that work draws on for a given
question — no new domain knowledge is introduced per-lens.

---

## 2. Functional roles (map 1:1 to architecture layers)

### Role: Question Understander
- **Responsibility:** Intent classification, metric resolution, dimension resolution, time
  resolution (`question_understanding_spec.md`).
- **Reads:** `semantic_metric_registry.csv`, `business_dimensions.md`.
- **Produces:** A resolved query object, or a clarification request, or a `NOT_DETERMINABLE`
  early exit.
- **Must never:** Compute a number. Guess a metric family member. Silently pick a definition.

### Role: Trust Gatekeeper
- **Responsibility:** Look up trust level, propagate conflict/DQ status through dependencies,
  return a binding verdict (`ai_trust_policy.md`, enforced structurally per
  `ai_analytics_architecture.md` Layer 3).
- **Reads:** `semantic_metric_registry.csv.trust_level`, `metric_dependency_graph.md` §6.
- **Produces:** SAFE / DISCLOSE / SHOW_BOTH / BLOCK / NOT_DETERMINABLE, with the specific
  `conflict_ids`/`dq_ids` responsible.
- **Must never:** Let a downstream role compute a single-number answer for a metric it has
  marked BLOCK. Downgrade a verdict based on how the question was phrased (per
  `ai_trust_policy.md` §2 BLOCK: "this includes rephrased, indirect, or comparative questions").

### Role: Analytics Executor
- **Responsibility:** Apply the metric's documented filters/aggregation/grain to the evidence
  layer; build trend/comparison/anomaly/driver plans (`analytics_execution_spec.md`).
- **Reads:** The evidence layer (via manifest resolution), `semantic_metric_registry.csv`'s
  execution-relevant columns.
- **Produces:** A `Result` object with value(s), grain, date basis, and validation status.
- **Must never:** Apply a filter, join, or aggregation not already documented for the metric.
  Silently substitute `created_at` for a business date. Compute a cross-family combination not
  documented in `metric_dependency_graph.md`.

### Role: Validator
- **Responsibility:** Compare the Executor's result against `validation_summary.csv`'s
  historical reference where one exists; run structural sanity checks
  (`analytics_execution_spec.md` §8).
- **Reads:** `validation_summary.csv`, the metric's `validation_reference`.
- **Produces:** A validation status (`MATCH`/`DIFFERS` with mechanism/`NOT_DETERMINABLE`) attached
  to the Result.
- **Must never:** Present an unverified result with the same confidence framing as a validated
  one. Silently accept a result that fails a sanity check.

### Role: Business Reasoner
- **Responsibility:** Climb the FACT→CALCULATION→OBSERVATION→INFERENCE→HYPOTHESIS→RECOMMENDATION
  ladder to the ceiling appropriate for the question's intent (`business_reasoning_spec.md`).
- **Reads:** The validated Result, `metric_dependency_graph.md`, `data_quality_report.md`.
- **Produces:** A sequence of epistemically-labelled statements.
- **Must never:** Phrase a HYPOTHESIS or RECOMMENDATION in FACT register. Climb higher than the
  question's intent warrants (§3 of `business_reasoning_spec.md`).

### Role: Insight Generator
- **Responsibility:** Proactive (unsolicited) surfacing of CRITICAL/HIGH-severity findings and
  notable trends/anomalies, per `insight_generation_spec.md`.
- **Reads:** `data_quality_report.md`'s severity/status columns, trend/anomaly output from the
  Analytics Executor.
- **Produces:** Ranked, evidence-backed insight candidates, each carrying the full Answer
  Contract.
- **Must never:** Surface an insight without a traceable metric_id/evidence chain. Manufacture
  urgency for a LOW/INFORMATIONAL-severity finding.

### Role: Answer Assembler
- **Responsibility:** Compose the final structured answer satisfying `answer_contract.md` in
  full, including evidence citations, confidence, and follow-up affordances.
- **Reads:** All upstream role outputs.
- **Produces:** The final answer object.
- **Must never:** Emit an answer with a required field missing. Flatten a SHOW_BOTH family's
  answer shape into a single scalar for brevity.

---

## 3. Role interaction rules

- **Roles execute in the pipeline order already fixed in `ai_analytics_architecture.md` §3** —
  Question Understander → Trust Gatekeeper → Analytics Executor → Validator → Business Reasoner
  → Insight Generator (only for proactive flows) → Answer Assembler. No role may be skipped, and
  no role may act on a question the upstream role has not yet resolved.
- **The Trust Gatekeeper's verdict is binding on every downstream role.** No later role may
  reinterpret or soften a BLOCK verdict — this is the single most important interaction rule in
  this document, because it is the structural guarantee behind `ai_trust_policy.md` §0 rule 3.
- **A role may request clarification from the user and pause the pipeline** (the Question
  Understander, primarily, per `question_understanding_spec.md` §6) — this is a legitimate
  pipeline outcome, not an error state.
- **Roles do not have independent "opinions."** Every role's output must be traceable to the
  semantic layer's own documented content — a role never introduces a fact, metric, or business
  rule the semantic layer doesn't already contain (this is the same hallucination-prevention
  discipline as `ai_analytics_architecture.md` §8, restated at the role-boundary level).

---

## 4. Why this is not "agents in code"

This document deliberately avoids specifying: agent communication protocols, tool-calling
schemas, autonomous planning loops, or inter-agent negotiation. Those are implementation
mechanics for a later phase. What this document fixes — and what must survive into whatever
implementation topology is eventually chosen, whether that is six separate services, six
functions in one process, or a single LLM call structured internally along these boundaries — is
**the separation of concerns and the non-negotiable ordering/binding rules in §3**. A monolithic
implementation that nonetheless respects "the Trust Gatekeeper's verdict is checked before any
number is computed for user-facing output" is compliant with this specification; a
sophisticated multi-agent implementation that lets a downstream agent bypass that check is not.
