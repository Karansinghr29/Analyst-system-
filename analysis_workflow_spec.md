# Analysis Workflow Specification

Specifies the deterministic workflows the Analyst Intelligence layer runs, and the point in each
at which it stops. Every workflow is assembled from Phase 1–5 stages; none introduces a
calculation of its own.

---

## 1. Metric question (the default)

```
owner question
  -> LLM question understanding        (proposes concept + intent; validated, untrusted)
  -> contract validation               (invalid never executes)
  -> conversation context              (additive-only inheritance)
  -> analytics plan                    (Phase 3; family expansion is mandatory)
  -> trust gate                        (Phase 2; binding)
  -> deterministic execution           (Phase 1/2 calculators)
  -> validation                        (80 checks + sanity checks that halt)
  -> business reasoning                (epistemic ladder, ceiling enforced)
  -> analyst role routing              (Phase 6)
  -> multi-lens synthesis              (Phase 6)
  -> decision support + answer contract
  -> guarded LLM verbalization
```

**Stops early, correctly, when:** the contract is invalid, the concept is ambiguous, an entity
cannot be identified, the period is outside coverage, or the concept is structurally absent.

---

## 2. "What changed?" — period comparison

```
for each comparable monthly metric:
    load month-keyed series
    drop INCOMPLETE periods            <- see §2.1
    compare last two complete periods
    classify: INCREASE / DECREASE / NO_CHANGE / UNAVAILABLE
    materiality: UNDEFINED, always
```

### 2.1 Incomplete-period exclusion

The export snapshot is **2026-08-29**, which is mid-month. Both 2026-09 (a few forward-dated
postings) and 2026-08 (29 of 31 days) are therefore only partially captured.

Comparing a partial month against a complete one manufactures a dramatic false signal. On this
dataset it reported revenue *"falling 99.86%"* — an artifact of the export cut-off, not a
business event. Reporting that to an owner would be precisely the data-artifact-as-business-signal
failure `business_reasoning_spec.md` §2's OBSERVATION gating rule exists to prevent.

Excluded periods are **named in the answer**, never silently dropped.

### 2.2 Materiality

`insight_generation_spec.md` §2 condition 3: *"this specification does not fix the threshold
value (an implementation-phase/business decision)."*

No threshold exists in the exported evidence or in any specification document. The classification
vocabulary therefore has **no "immaterial" value** — calling a change immaterial requires the
threshold that does not exist. Direction and size are reported; significance is an owner
judgement this system does not substitute for.

### 2.3 What is never compared

- A **SHOW_BOTH/BLOCK** metric — comparing periods would require choosing one definition, which
  is the silent resolution the trust policy forbids.
- A **composite monthly value** (e.g. `M.PNL.001`'s `{revenue, expenses, …}`) — picking one
  component as "the" change is a definition decision this layer may not make.

Both are returned as `UNAVAILABLE` **with their reason**, never omitted.

---

## 3. "Why?" — driver analysis

```
target metric
  -> detect its own period change
  -> walk ONLY documented dependency edges (semantic_metric_registry.dependency_metrics)
  -> for each component, detect its change
  -> emit: FACT -> CALCULATION -> OBSERVATION -> INFERENCE -> HYPOTHESIS
```

**The ladder stops at HYPOTHESIS.** `business_reasoning_spec.md` §3 sets a driver question's
ceiling there, and no recommendation is emitted unasked.

**No causal claim is ever made.** The exported evidence contains no experiment and no control.
What can be established is that a *documented edge exists* and that the component *moved in the
same window* — a pattern, labelled as one. Every driver carries:

> "This is a correlation over a documented dependency edge, not a demonstrated cause."

A conflicted target decomposes **per definition** and is never merged
(`analytics_execution_spec.md` §2.6).

A metric with no documented edges says so and returns
**"Not determinable from exported evidence."**

---

## 4. Management briefing

Assembles seven sections (`executive_summary.py`). Every KPI line passes the same trust rules a
reactive answer does:

| Trust | Briefing behaviour |
|---|---|
| SAFE / DISCLOSE | value shown; DISCLOSE carries its caveat |
| SHOW_BOTH / BLOCK | **no single figure**; every definition listed, labelled |
| NOT_DETERMINABLE | exactly "Not determinable from exported evidence." |

A KPI that cannot be shown safely is **still listed**, with the reason. Omitting it would let a
briefing read as "nothing to report here" when the truth is "this cannot be reported as one
number" — the opposite of what an owner needs.

---

## 5. Decision support

Every recommendation carries evidence, impact (or a stated reason none is determinable), risk,
confidence from the documented vocabulary (`PROVEN`/`SUSPECTED`, never a percentage), the action,
and what evidence would change it.

**The BLOCK rule** (`business_reasoning_spec.md` §2, the sharpest gate in the document set): a
recommendation touching a BLOCK metric must recommend **resolving the conflict** — an owner
decision on which definition is authoritative — never an operational action on a disputed figure.

---

## 6. Trust posture ("which numbers can I trust?")

Buckets all 49 metrics by their gate verdict and states what each level means in business terms.
The trust levels are the semantic layer's own, unchanged by this layer.

---

## 7. Explainability

Any answer expands into the evidence chain of `analyst_intelligence_spec.md` §8. Links that are
legitimately empty (no recommendation for a lookup; no calculation for a refusal) are declared
with their documented reason.
