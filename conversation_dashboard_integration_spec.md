# Conversation ↔ Dashboard Integration Specification

The dashboard and the conversation are one system with two surfaces. Clicking a card continues a
conversation; a conversational answer is renderable as a card. **They cannot disagree**, because
neither computes anything — both read the same executed answers.

---

## 1. The five click paths

| Owner clicks | Becomes | Answered by |
|---|---|---|
| **Why?** on a change | driver question about that metric | `root_cause.py` — documented edges only |
| **Drill down** on a tile | grouped lookup on a supported dimension | `analytics_planner.py` — grain-checked |
| **What should I do?** on an insight | that insight's recommendation | `insight_engine.py` + decision support |
| **How was this calculated?** on a metric | calculation + evidence chain | `explainability.py` |
| **Which number is correct?** on a conflict | all definitions + owner-decision statement | conflict panel |

The fifth is the one that must not be "helpful". The correct answer to *"which number is
correct?"* is not a number:

> Three definitions of profit exist and they disagree. Which is authoritative is a business
> decision, not an analytical one. Here is what each measures, what each yields, and what
> deciding between them would settle.

---

## 2. Context carried across the boundary

When a click becomes a question, the context is **seeded, not re-derived**:

| Carried | From |
|---|---|
| metric_id(s) | the card |
| period | the card's as-of / selected period |
| dimensions & filters | the active dashboard filter state |
| entity | the selected row, if a detail table |
| trust posture | re-read from the gate, never carried |

**Trust is never inherited.** `answer_contract.md` §6: the contract has no caching concept that
could serve a stale trust posture. Every turn re-reads the gate.

---

## 3. Conversation state rules

Carried forward from Phase 5, unchanged:

1. **Additive only.** Inheritance fills fields the new question left empty. There is no code path
   that overwrites a stated value.
2. **Explicit wins.** "What about June?" keeps the metric, replaces the period.
3. **Correction replaces.** "No, I meant occupancy" drops inherited context entirely.
4. **Ambiguity survives.** A SHOW_BOTH family stays SHOW_BOTH across follow-ups; repetition does
   not wear it down.
5. **An unanswered clarification is never permission.** Five distinguishable states —
   `REQUIRED`, `ANSWERED`, `REJECTED`, `STILL_AMBIGUOUS`, `INSUFFICIENT_EVIDENCE`. "You decide"
   is a refusal to choose, not authority to choose.
6. **Narrowing requires an explicit, unambiguous selection** made *after* the alternatives were
   shown. Even then the conflict is still disclosed — selection changes which figure leads, never
   the fact that others exist.
7. **Reset clears everything** — turns, pending clarification, and recorded selections.

---

## 4. Drill from executive insight to source record

```
Owner Dashboard tile
  → metric card (value, trust, conflicts, DQ)
    → trend / period comparison
      → breakdown by a supported dimension
        → detail table
          → source record (manifest-resolved CSV row)
            → the validation check that confirmed the reconstruction
```

Trust, conflicts and caveats travel down **every** level. A drill-down never sheds the
qualification that applied at the top — which is the failure mode that makes BI drill-downs
dangerous: a caveated total whose detail rows appear uncaveated.

---

## 5. Bidirectionality

A conversational answer carries everything a card needs (`bi_contract.py`), so any answer can be
pinned to the dashboard. A pinned answer is re-executed on view, not cached — the trust posture
must be current.

---

## 6. What integration must never allow

| Never | Why |
|---|---|
| A dashboard filter that changes a metric's definition | Filters narrow; they do not redefine |
| A drill-down that drops a caveat | The caveat qualifies the detail as much as the total |
| Cross-filtering across competing definitions | Would silently mix incompatible measures |
| A pinned card serving a stale trust level | Trust changes must propagate immediately |
| Context inheritance overriding an explicit constraint | The owner's stated value always wins |
| A click producing a figure the conversation would refuse | Both surfaces share one gate |
