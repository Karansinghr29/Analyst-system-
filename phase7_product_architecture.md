# Phase 7 — Product Architecture

The complete AI Business Analytics + Business Analyst + BI + Decision Support product, built on
the Phase 1–6 foundation without weakening any part of it.

**This document specifies a product. It invents no business content.** Every metric, dimension,
conflict, DQ finding, and trust level it references already exists in the semantic layer.
`scripts/validate_phase7_consistency.py` proves that mechanically: it reads every Phase 7
document and registry, extracts every symbol, and checks each against the live system. A document
that names a metric the registry lacks, or asserts a trust level the gate does not assign, fails
that check.

---

## 1. The three ways in

The product principle is that the owner should never be *required* to ask a question:

| Entry | Surface | Built on |
|---|---|---|
| **Look** — understand the business without asking | Owner Executive Dashboard | `executive_summary.py`, `bi_contract.py` |
| **Ask** — any supported business question | Conversation | `analyst_intelligence.py` → Phase 1–5 pipeline |
| **Decide** — "what should I do / why / what's wrong" | Decision Queue | `insight_engine.py`, `root_cause.py` |

All three read the **same** computed answers. There is no second calculation path, so the
dashboard and the conversation cannot disagree.

---

## 2. Layer stack

```
 ┌────────────────────────────────────────────────────────────────────┐
 │ L9  Owner UI            dashboard · conversation · decision queue  │  ← not built yet
 ├────────────────────────────────────────────────────────────────────┤
 │ L8  LLM verbalization   UNTRUSTED · guarded · discardable          │
 ├────────────────────────────────────────────────────────────────────┤
 │ L7  Decision support    recommendations, owner decisions            │
 │ L6  Insight generation  proactive findings, ranked                  │
 │ L5  Role / lens routing 9 analyst lenses over one semantic layer    │
 │ L4  Business reasoning  FACT→CALC→OBS→INF→HYP→REC, ceiling-gated    │
 ├────────────────────────────────────────────────────────────────────┤
 │ L3  Validation          80 checks + sanity checks that HALT         │
 │ L2  Analytics execution deterministic calculators                   │
 │ L1  Trust / conflict    BINDING verdict, computed before execution  │
 ├────────────────────────────────────────────────────────────────────┤
 │ L0  Semantic layer      49 metrics · dimensions · conflicts · DQ    │
 │     Evidence            253 immutable CSVs, manifest-resolved       │
 └────────────────────────────────────────────────────────────────────┘
```

**The deterministic/LLM boundary is L8.** Everything below it computes; L8 only re-words. A
verbalization that introduces a number, drops a caveat, collapses a conflicted family, produces a
BLOCK headline, or surfaces PII is **discarded whole** and the deterministic skeleton is shown
instead. Safety therefore never depends on the model cooperating.

---

## 3. What each layer may and may not do

| Layer | May | May never |
|---|---|---|
| L0 Evidence | Be read | Be modified — the 253 CSVs are immutable |
| L1 Trust gate | Tighten a verdict | Loosen one, or be overridden by any later layer |
| L2 Execution | Apply documented filters/aggregations | Invent a filter, join, or date basis |
| L3 Validation | Compare against the 80 checks; halt on a sanity failure | Silently emit a result that failed a check |
| L4 Reasoning | Climb to the intent's ceiling | Assert a cause; exceed the ceiling unasked |
| L5 Lens routing | Foreground existing content | Introduce a metric or change a trust level |
| L6 Insights | Fire the two implementable triggers | Invent a threshold to fire the other two |
| L7 Decisions | Recommend, grounded in evidence | Recommend action on a disputed figure |
| L8 LLM | Interpret language; re-word a skeleton | Calculate, choose a definition, or override L1 |

---

## 4. Trust rendering — one rule, every surface

The same five-way rule governs the dashboard, every role view, every BI card, the briefing, the
insight feed, and every conversational answer. It is machine-readable in
`owner_dashboard_registry.csv` and `conflict_disclosure_registry.csv`, not left to a UI author:

| Trust | Widget | Rule |
|---|---|---|
| `SAFE` | `kpi_card` | Single value with validation status |
| `DISCLOSE` | `kpi_card_with_caveat` | Value **and** caveat together — never a tooltip the owner may not open |
| `SHOW_BOTH` | `multi_definition_panel` | Every definition, labelled, plus the spread. No default, no average |
| `BLOCK` | `conflict_panel_no_headline` | **No figure.** Explanation, each definition, the owner decision |
| `NOT_DETERMINABLE` | `not_determinable_notice` | The exact sentence "Not determinable from exported evidence.", plus what is missing. No chart, no zero |

Current dashboard: **20 tiles, 3 of which may not render a headline** (`M.AR.001A`,
`M.OCC.001`, `M.PROFIT.001`).

---

## 5. Determinism

The evidence is immutable, so the same question asked twice returns the same answer. This is a
requirement, not a property that happens to hold: `answer_contract.md` §6 makes it explicit, and
it is tested at every layer. The one non-deterministic field is `computed_at`; determinism is
asserted over `contract_identity()`, which excludes it.

---

## 6. What the product will not do

Each refusal is a consequence of the evidence, not a missing feature:

| Refusal | Because |
|---|---|
| Classify a change as material | No threshold exists — `insight_generation_spec.md` §2 condition 3 defers it to a business decision |
| Detect anomalies | `analytics_execution_spec.md` §2.5 leaves the statistical method open |
| Assert a cause | No experiment or control exists in the evidence |
| Compare properties | One property exists; the answer is that structural fact |
| Quote a benchmark | The evidence contains only this business's own records |
| Resolve a definition conflict | Only an owner may decide which definition is authoritative |

---

## 7. Consistency guarantee

`scripts/validate_phase7_consistency.py` runs nine checks across all 13 documents and 3
registries, and fails on any drift. It also re-hashes all 253 source CSVs against the recorded
baseline, so a specification change that touched evidence would be caught immediately.
