# Owner Intelligence — Product Capability Audit

Audited against the code and exported evidence as they stand. No capability is listed unless
something in the repository implements or explicitly refuses it.

**Status vocabulary**

| Status | Meaning |
|---|---|
| `IMPLEMENTED` | Works end to end and reaches the owner |
| `PARTIALLY_IMPLEMENTED` | Works for some inputs, or computes but does not surface |
| `MISSING` | Nothing implements it; nothing blocks it either |
| `BLOCKED_BY_EVIDENCE` | The export cannot support it; refusing is the correct behaviour |
| `BLOCKED_BY_BUSINESS_DECISION` | Implementable, but needs a threshold or definition only the owner can set |

The last two are **not defects**. They are the system declining to invent, and the product
discloses them through `analysis_capability_registry.csv` → `engine/capability_disclosure.py`.

---

## 1. Data Analyst

| Capability | Current implementation | Location | Status | Remaining gap | Blocks prod | Next step |
|---|---|---|---|---|---|---|
| KPI analysis | 49 metrics execute with trust, validation, citations | `engine/execution.py` | IMPLEMENTED | — | No | — |
| Trends | Monthly series plan type | `engine/analytics_planner.py` (`PLAN_TREND`) | IMPLEMENTED | Only 3 metrics expose a month-keyed series | No | — |
| Comparisons | Period comparison honouring requested periods | `engine/change_detection.py` | IMPLEMENTED | — | No | — |
| Segmentation | property / tenant / month dimensions | `engine/dimension_resolution.py` | IMPLEMENTED | Degenerate dims (1 property) correctly refused | No | — |
| Patterns | Standing findings from the insight engine | `engine/insight_engine.py` | IMPLEMENTED | — | No | — |

## 2. Data Scientist

| Capability | Current implementation | Location | Status | Remaining gap | Blocks prod | Next step |
|---|---|---|---|---|---|---|
| Forecasting | Detected and refused with the subject preserved | `time_resolution.asks_unsupported_forecast`, `owner_presentation` | BLOCKED_BY_EVIDENCE | A snapshot export contains no forward evidence | No | Leave refused |
| Anomaly detection | `PLAN_ANOMALY` exists; no threshold to fire on | `engine/analytics_planner.py` | BLOCKED_BY_BUSINESS_DECISION | `analytics_execution_spec.md 2.5` leaves the method unfixed | No | Owner sets an anomaly bound |
| Statistical analysis | Registry declares `statistical_summary` NOT_IMPLEMENTED | `analysis_capability_registry.csv` | BLOCKED_BY_BUSINESS_DECISION | No statistical method specified anywhere | No | Owner/analyst chooses a method |
| Prediction | Same path as forecasting | as above | BLOCKED_BY_EVIDENCE | — | No | Leave refused |
| Capability-aware limits | Every section renders "Not available, and why" | `engine/capability_disclosure.py`, `views/analytics.js` | IMPLEMENTED | — | No | — |

## 3. Business Analyst

| Capability | Current implementation | Location | Status | Remaining gap | Blocks prod | Next step |
|---|---|---|---|---|---|---|
| What changed | Complete-month comparison, partial periods refused | `engine/change_detection.py` | IMPLEMENTED | — | No | — |
| Why / driver analysis | Documented dependency edges only | `engine/root_cause.py` | IMPLEMENTED | No correlation-derived causes, by design | No | — |
| Business interpretation | Epistemic ladder with per-intent ceilings | `engine/business_reasoning.py` | IMPLEMENTED | — | No | — |
| Follow-up questions | Turn history + structured request persisted | `conversation_context.py`, `api/conversation_store.py` | IMPLEMENTED | — | No | — |
| Clarification | Fires on genuine ambiguity only | `engine/clarification_manager.py` | PARTIALLY_IMPLEMENTED | Some evidence gaps still surface as "rephrase your question" rather than the reason | **Yes** | Route capability gaps to their reason, not a generic clarifier |

## 4. Financial Analyst

| Capability | Current implementation | Location | Status | Remaining gap | Blocks prod | Next step |
|---|---|---|---|---|---|---|
| Revenue | SAFE, reconciled to the exported reference | `calculators/financial.py` | IMPLEMENTED | — | No | — |
| Expenses | SAFE | `calculators/financial.py` | IMPLEMENTED | — | No | — |
| Profit | 3 competing definitions, BLOCK enforced | `calculators/financial.py` | BLOCKED_BY_BUSINESS_DECISION | Owner must name the official definition | No | Owner decision, then the gate follows |
| Collections | 2 definitions, disclosed | `calculators/collections_.py` | IMPLEMENTED | — | No | — |
| Receivables | 4 definitions, SHOW_BOTH | `calculators/receivables.py` | BLOCKED_BY_BUSINESS_DECISION | Owner must name the official definition | No | Owner decision |
| Deposits | SAFE | `calculators/deposits.py` | IMPLEMENTED | — | No | — |

## 5. Operations Analyst

| Capability | Current implementation | Location | Status | Remaining gap | Blocks prod | Next step |
|---|---|---|---|---|---|---|
| Occupancy | 5 definitions, SHOW_BOTH; availability from source status | `calculators/occupancy.py` | IMPLEMENTED | Denominator disagreement is a disclosed conflict, not a bug | No | — |
| Beds | Bed-grain occupancy has no exported reference | `M.OCC.004` | BLOCKED_BY_EVIDENCE | — | No | Leave refused |
| Maintenance | Volume and ageing | `calculators/maintenance.py` | IMPLEMENTED | 20-month span forbids YoY | No | — |
| Electricity | Usage and cost | `calculators/eb.py` | IMPLEMENTED | 1–5 month span forbids trend | No | — |
| Move-in / move-out | Lifecycle event counts | `calculators/occupancy.py` | IMPLEMENTED | — | No | — |
| Utilization | `bed_utilization` PARTIAL | `analysis_capability_registry.csv` | BLOCKED_BY_EVIDENCE | Apartment/bed-grain metrics NOT_DETERMINABLE | No | Leave refused |

## 6. Risk Analyst

| Capability | Current implementation | Location | Status | Remaining gap | Blocks prod | Next step |
|---|---|---|---|---|---|---|
| Risks | Risk composite scan, no blended score | `analytics_planner.py` (`PLAN_RISK_COMPOSITE`) | IMPLEMENTED | — | No | — |
| Data-quality issues | 32 findings, severity-ordered | `engine/insight_engine.py` | IMPLEMENTED | — | No | — |
| Exceptions | DQ + validation divergences | `engine/validator.py` | IMPLEMENTED | — | No | — |
| Exposure | Affected amounts where recorded | `calculators/risk_dq.py` | PARTIALLY_IMPLEMENTED | Amount present per finding; no portfolio total | No | Sum only where the evidence supports it |
| Conflicts | 12 conflicts surfaced, never resolved | `engine/insight_engine.py`, gate | IMPLEMENTED | — | No | — |

## 7. Decision Support

| Capability | Current implementation | Location | Status | Remaining gap | Blocks prod | Next step |
|---|---|---|---|---|---|---|
| What needs attention | 11-item queue on Home and in chat | `engine/executive_summary.py` | IMPLEMENTED | — | No | — |
| Priorities | Deterministic ranking; no invented score | `engine/insight_ranker.py` | IMPLEMENTED | — | No | — |
| Actionable insights | Recommendations gated by the ladder | `engine/business_reasoning.py`, `decision_support.py` | IMPLEMENTED | — | No | — |
| Trade-offs | Not built | `engine/decision_support.py` | MISSING | No option/consequence model exists | No | Only if evidence supports comparing options |

## 8. AI Business Analyst

| Capability | Current implementation | Location | Status | Remaining gap | Blocks prod | Next step |
|---|---|---|---|---|---|---|
| Arbitrary owner questions | Concept map + planner + Ollama interpretation | `engine/llm_interface.py` | PARTIALLY_IMPLEMENTED | Small local model fails on some phrasings; falls back safely | No | Larger model, or extend the deterministic concept map |
| NL paraphrases | Normaliser incl. Tamil-English | `engine/question_normalize.py` | IMPLEMENTED | — | No | — |
| Follow-up context | Inherits subject, never permission | `conversation_context.py` | IMPLEMENTED | — | No | — |
| Period-aware questions | Requested periods preserved end to end | `time_resolution.py`, `change_detection.py` | IMPLEMENTED | — | No | — |
| Conflict-aware answers | BLOCK / SHOW_BOTH enforced in chat | `answer_renderer.py` guard | IMPLEMENTED | — | No | — |
| Honest capability gaps | Refusals carry the exact phrase | `owner_presentation.py` | IMPLEMENTED | — | No | — |
| Owner "Why?" | Trust-keyed narrative, no internals | `explainability.owner_projection` | IMPLEMENTED | — | No | — |
| Verbalization latency | ~20–115 s per answer on local CPU | `engine/prompt_contracts.py` | PARTIALLY_IMPLEMENTED | Too slow for interactive use; 2 of 5 answers fall back | **Yes** | Faster model or GPU; deterministic text already correct |

## 9. Power BI

| Capability | Current implementation | Location | Status | Remaining gap | Blocks prod | Next step |
|---|---|---|---|---|---|---|
| Executive | Page renders home tiles + insights | `frontend/views/powerbi.js`, `bi_nav.js` | IMPLEMENTED | — | No | — |
| Financial | Analytics section slice | same | IMPLEMENTED | — | No | — |
| Operations | Analytics section slice | same | IMPLEMENTED | — | No | — |
| Risk / Data Quality | DQ centre embedded | same | IMPLEMENTED | — | No | — |
| Insights / Attention | Insight feed + decision queue | same | IMPLEMENTED | — | No | — |
| External Power BI dataset | Descriptor generated, never imported | `powerbi_dataset_descriptor.json` | PARTIALLY_IMPLEMENTED | No Power BI workspace consumes it | No | Only when a workspace exists |

## 10. Owner Home

| Capability | Current implementation | Location | Status | Remaining gap | Blocks prod | Next step |
|---|---|---|---|---|---|---|
| Executive snapshot | Health, operations, risk, trust summary | `frontend/views/dashboard.js` | IMPLEMENTED | — | No | — |
| Attention | Decision queue + critical findings + changes | same | IMPLEMENTED | — | No | — |
| Key insights | Positive/opportunity + next steps | same | IMPLEMENTED | — | No | — |
| First-load latency | Warmed at startup, ~1 s served | `serve.py`, `api/service.py` memo | IMPLEMENTED | Cold build is tens of seconds, paid once | No | — |

---

## Totals

**48 capabilities audited**

| Status | Count |
|---|---|
| IMPLEMENTED | 35 |
| PARTIALLY_IMPLEMENTED | 6 |
| MISSING | 1 |
| BLOCKED_BY_EVIDENCE | 4 |
| BLOCKED_BY_BUSINESS_DECISION | 4 (*counting profit + receivables definitions as owner decisions*) |

Only **2 of 48 block production**, and neither is an analytics defect.

## Top 5 remaining gaps

1. **LLM verbalization latency** — 20–115 s per answer on local CPU; 2 of 5 smoke answers
   fell back to deterministic text. The answers are correct; the wait is not usable. *Blocks production.*
2. **Generic clarification masking real reasons** — some evidence gaps still surface as
   "rephrase your question", blaming the owner's wording for a limit of the export.
   *Blocks production.* This is the residue of the 13 known pre-existing test failures.
3. **Terminal plans build no audit skeleton** — `result.rendered` is `None` on refusal paths, so
   an answer the owner *did* receive has no lineage record. An audit gap, not an owner-visible one.
4. **Owner decisions outstanding** — profit (3 definitions) and receivables (4) stay BLOCK/SHOW_BOTH
   until the owner names the official definition. Correct behaviour; still unresolved business state.
5. **Risk exposure has no portfolio total** — per-finding amounts exist, no aggregate. Only worth
   doing where the evidence supports summing.

## Recommended implementation order

1. **Verbalization performance** — the only gap that makes the product feel broken. Try a smaller/faster
   local model or GPU before touching any code; the pipeline and guard are already correct.
2. **Clarification routing** — make capability and evidence gaps state their reason instead of a
   generic rephrase prompt. Closes gap 2 and most of the 13 known failures.
3. **Audit skeleton on terminal plans** — small, unblocks `test_block_remains_blocked` honestly.
4. **Owner decision workflow** — a surface to record "profit means Def A", feeding the existing
   `DefinitionSelection` store. Converts two BLOCKs into answerable metrics without weakening the gate.
5. **Leave 3, 4, 5 of the gap list alone otherwise** — anomaly, statistics and forecasting are
   correctly refused. Implementing them requires thresholds the evidence does not contain, and
   inventing one would be the single most damaging change available.

---

*Audit only. Nothing in this document has been implemented.*
