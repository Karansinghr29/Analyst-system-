# AI Chat Experience Specification

The always-available AI Business Analyst surface.

**It calls the same pipeline as everything else.** Phase 8 brief 4: "Do NOT create a second
analytics path inside the UI." A typed question and a clicked tile both reach
`AnalystIntelligence.ask()`, so the chat and the dashboard cannot disagree.

---

## 1. Question entry

A persistent global input: *"Ask anything about your business…"*, with suggested questions drawn
from `ai_entrypoint_registry.csv` (111 registered entry points):

- How is my business doing?
- What changed this month?
- Why did profit change?
- What should I focus on?
- What are my biggest risks?
- Show me revenue trends.
- Explain collections.
- Can I trust the receivables number?

Every suggestion is validated against the engine: check 11 of the Phase 8 validator resolves each
registered question and fails if any produces no valid plan.

---

## 2. The answer panel

Every answer renders the same nine parts:

```
ANSWER                  the figure, or why there is not one
WHAT THIS MEANS         business-language interpretation
EVIDENCE                manifest keys → source CSVs
CALCULATION             filters, aggregation, date basis, policies
CONFIDENCE              HIGH / MEDIUM / SPLIT / BLOCKED / UNVERIFIED
CAVEAT                  mandatory for DISCLOSE, never collapsed away
RELATED INSIGHTS        findings touching this metric
RECOMMENDED NEXT        the questions this answer makes worth asking
[Ask follow-up]
```

Levels beyond the first are one interaction away, never removed.

---

## 3. The verbalization guard is authoritative

The LLM re-words a finished deterministic skeleton. Its output is **untrusted** and is checked
before display. A verbalization is **discarded whole** — not partially used — if it:

- introduces a number absent from the skeleton
- drops a mandatory caveat
- collapses a SHOW_BOTH family
- produces a headline for a BLOCK metric
- omits the exact NOT_DETERMINABLE phrase where required
- references PII

On rejection the deterministic skeleton is shown. **The UI must never expose an LLM-generated
number that was not in the skeleton**, and it cannot, because the guard runs server-side before
the payload is built.

---

## 4. Behaviour by trust level

| Trust | Chat answer |
|---|---|
| SAFE | The figure, with evidence and validation |
| DISCLOSE | The figure **with** its caveat |
| SHOW_BOTH | Every definition labelled, plus the spread. Never one number |
| BLOCK | No figure. Why not, each definition, the owner decision needed |
| NOT_DETERMINABLE | *Not determinable from exported evidence.* plus what is missing |

---

## 5. Conversation continuity

Context inherits **additively only**. A field the owner stated is never overwritten:

```
"Show revenue for July."  →  "What about June?"
   inherits the metric · replaces the period (June was explicit)

"How much revenue last month?"  →  "Why was it lower?"
   inherits metric + period · becomes a driver question
```

A **correction** ("no, I meant occupancy") drops inherited context rather than extending it.

A **definition selection** is honoured only after the alternatives were shown, and only when
unambiguous. "Use the live occupancy definition" matches three of five labels, so the system asks
which — picking one would be silent narrowing; ignoring it would leave an explicit instruction
unacknowledged.

An **unanswered clarification is never permission**. Five states: `REQUIRED`, `ANSWERED`,
`REJECTED`, `STILL_AMBIGUOUS`, `INSUFFICIENT_EVIDENCE`. "You decide" is a refusal to choose, not
authority to choose.

---

## 6. What the chat never does

| Never | Why |
|---|---|
| Compute a number | It has no calculation path |
| Choose a conflict definition unasked | Requires explicit owner selection |
| Assert a cause | Drivers arrive labelled OBSERVATION/HYPOTHESIS |
| Estimate a NOT_DETERMINABLE value | Exact-phrase requirement |
| Surface PII | Guard over the 27 excluded columns |
| Invent a threshold | Materiality and anomaly report as undefined |
