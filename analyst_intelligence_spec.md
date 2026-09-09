# Analyst Intelligence Specification

Specifies the Virtual Business Analyst layer: how one deterministic system behaves as nine
analyst lenses over the *same* semantic layer, without any lens being able to change a number, a
definition, or a trust verdict.

**This layer adds no business content.** Every metric, dimension, date field, conflict, and DQ
finding it uses already exists in Phases 1–5. What Phase 6 adds is four things: lens routing,
multi-lens synthesis, whole-business workflows (briefing / what-changed / why / what-to-do), and
the explainability chain.

---

## 1. The governing principle

`ai_agent_roles.md` §1 already settled the central question, and this layer implements its
answer rather than inventing a parallel one:

> "The brief asks for a system that behaves as a combination of Data Analyst, Data Scientist, BI
> Analyst, Business Analyst, Financial Analyst, and Operations Analyst. These are **not** six
> separate functional roles to implement — they are six **domain lenses** the same underlying
> functional pipeline must be able to apply."

A lens therefore selects **which already-existing semantic content is foregrounded**. It never
recomputes, re-defines, or re-grades anything. Three invariants follow, all enforced in code and
tested:

| Invariant | Enforced by |
|---|---|
| A lens cannot introduce a metric | `analyst_roles.verify_against_registry()`; lenses claim `domain` values, not metric lists |
| A lens cannot change a trust level | trust comes from `engine/gate.py`; no lens writes it |
| A lens cannot contradict another | every lens reads the *same* executed answers |

---

## 2. The nine lenses

Six are defined by `ai_agent_roles.md` §1. Three are **Phase 6 compositions** of machinery that
already exists — marked as such in `analyst_role_registry.csv`'s `origin` column, so the
distinction between "the spec said so" and "Phase 6 assembled it" stays visible.

| Lens | Origin | Owns domains |
|---|---|---|
| Data Analyst | `ai_agent_roles.md` §1 | all three |
| Business Analyst | `ai_agent_roles.md` §1 | Financial, Operations |
| Financial Analyst | `ai_agent_roles.md` §1 | Financial |
| Operations Analyst | `ai_agent_roles.md` §1 | Operations |
| Data Scientist / Diagnostic | `ai_agent_roles.md` §1 | all three |
| BI Analyst | `ai_agent_roles.md` §1 | all three |
| Management Reporting Analyst | Phase 6 composition | all three |
| Decision-Support Analyst | Phase 6 composition | all three |
| Risk / Data-Quality Analyst | Phase 6 composition | Risk & Data Quality |

Each lens declares a `never_does` boundary. The two that matter most:

- **Financial Analyst** — *never* states a single financial truth where the evidence carries
  competing definitions.
- **Data Scientist** — *never* applies a statistical method or threshold the specifications do
  not define. `analytics_execution_spec.md` §2.5 leaves the anomaly method open, so no anomaly
  threshold is invented.

---

## 3. Routing (the owner never chooses a lens)

Routing is deterministic and derived from two things that already exist: the resolved metric's
`domain` column, and the question's intent.

```
1. domain lens of the metric actually answered   -> most direct, leads
2. intent-driven lenses                          -> lookup/trend/driver/risk/recommendation
3. risk-DQ lens, whenever trust != SAFE          -> the conflict is part of the answer
4. BI + business lens, on a structural limitation -> "only 1 property exists" is a business fact
```

Worked examples, all tested in `tests/test_analyst_routing.py`:

| Question | Lenses |
|---|---|
| "Why did profit fall?" | Financial + Data Scientist + Business + Risk/DQ |
| "What is occupancy?" | Operations + Data Analyst + Risk/DQ |
| "Which expense category is largest?" | Financial + Data Analyst |
| "Which property is performing better?" | Data Analyst + BI + Business → **structural limitation** |
| "What data should I worry about?" | Risk/DQ |

---

## 4. Multi-lens synthesis

> "The final answer should combine the lenses without duplicating or contradicting metrics."

Two rules achieve this:

1. **A metric appears under exactly one lens** — the most direct one that claimed it. Later
   lenses see it already claimed and do not restate it.
2. **Contradiction is structurally impossible, not merely unlikely** — every lens reads the same
   executed `MetricAnswer` objects. There is no second computation to disagree with.

---

## 5. Whole-business workflows

Four owner intents are routed *before* metric resolution, because they resolve to no single
metric and would otherwise terminate as `NOT_DETERMINABLE` — which would be true of the metric
lookup and false of the question.

| Owner phrasing | Workflow |
|---|---|
| "How is the business doing?" | management briefing (`executive_summary.py`) |
| "What changed this month?" | change detection (`change_detection.py`) |
| "What should I do?" | decision support (`executive_summary.py` attention + actions) |
| "Which numbers should I trust?" | trust posture across all 49 metrics |

---

## 6. What this layer will not do

| Refusal | Reason |
|---|---|
| Classify a change as material | No threshold exists — `insight_generation_spec.md` §2 condition 3 leaves it to a business decision |
| Assert a cause | The evidence contains no experiment or control; driver analysis reports patterns over documented edges only |
| Compare properties | One property exists; the answer is the structural fact, not a ranking |
| Derive a rate the registry does not define | Forming one requires choosing a denominator the semantic layer does not document |
| Supply a benchmark | The evidence contains only this business's own records |
| Resolve a definition conflict | Only an owner may decide which definition is authoritative |

Each refusal returns the exact phrase **"Not determinable from exported evidence."**

---

## 7. Pipeline position

```
Evidence → Semantic Layer → Question Understanding → Analyst Role Routing →
Metric Resolution → Dimension Resolution → Time Resolution → Analytics Plan →
Trust Gate → Deterministic Calculation → Validation → Business Reasoning →
Multi-Lens Analysis → Insight Generation → Decision Support → Answer Contract →
LLM Verbalization → Owner-Friendly Answer
```

The LLM remains downstream of every authoritative computation. `tests/test_multi_lens_analysis.py`
pins that the briefing is complete with the LLM disabled entirely.

---

## 8. Explainability

Any answer can be expanded into the chain in `explainability.py`:

```
question → interpretation → analyst role → metric → calculation → source evidence →
validation → trust decision → reasoning → recommendation
```

Nothing in the chain is computed; every link is read from an object an earlier stage produced.
A link that cannot be filled is declared a gap with its documented reason, never narrated over.
