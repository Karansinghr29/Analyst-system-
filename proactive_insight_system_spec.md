# Proactive Insight System Specification

What the system surfaces to the owner **without being asked**, and — equally specified — what it
refuses to surface because the evidence cannot support it.

`insight_generation_spec.md` §1 fixes the standard an unsolicited finding must meet:

> "an insight is not a different KIND of output, it is an answer the system generated without
> being asked, and it must satisfy every requirement a reactive answer does."

So every trust rule applies unchanged. There is no relaxed standard for proactive content.

---

## 1. The four triggers, and why two do not fire

`insight_generation_spec.md` §2 defines exactly four triggers and states "no other trigger source
is in scope."

| # | Trigger | Status | Findings |
|---|---|---|---|
| 1 | CRITICAL/HIGH DQ finding | **fires** | 12 |
| 2 | Anomaly outside history | **cannot fire** | — |
| 3 | Material period delta | **cannot fire** | — |
| 4 | Documented risk boundary crossed | **fires** | 4 |
| §5 | Definition conflict | **fires** | 4 |

**Total: 20 standing insights.**

Triggers 2 and 3 do not fire because their firing conditions are deliberately left open by the
specifications themselves:

> §2.5 of `analytics_execution_spec.md`: *"the specific statistical method is an
> implementation-phase decision, not fixed by this specification."*
>
> §2 condition 3 of `insight_generation_spec.md`: *"this specification does not fix the threshold
> value (an implementation-phase/business decision)."*

No threshold for either exists anywhere in the exported evidence. Inventing one would make every
insight produced under it an artifact of a number this project made up — the same class of
violation as inventing a metric. So the system **reports the gap** rather than reporting zero
findings as if it had looked and found nothing.

Trigger 4 needs no threshold: the diagnostic's own definition *is* the boundary, so a non-empty
result set is the crossing.

---

## 2. Separation of epistemic kinds

The brief requires these be kept apart, and `insight_models.py` keeps them in separate fields:

| Kind | Field | Example |
|---|---|---|
| **Proven fact** | `fact` | A DQ finding's recorded row count |
| **Calculation** | `calculation` | A metric value computed from evidence |
| **Validated change** | `observation` | Direction and size over complete periods |
| **Definition conflict** | `conflict_ids` + all definitions | The 4-way AR disagreement |
| **DQ warning** | `dq_ids` | DQ.002, DQ.019, … |
| **Risk boundary** | trigger 4 findings | 214 overlapping allotments |
| **Hypothesis** | `hypothesis`, hedged, `SUSPECTED` | "consistent with … would explain if confirmed" |
| **Recommendation** | `recommendation`, recommendation register | "Recommend an owner decision on …" |

A hypothesis is **never** presented as a fact. Hedge language is required and tested; fact-register
phrasing is rejected.

---

## 3. Ranking

`insight_generation_spec.md` §4's four dimensions, compared **lexicographically and never
blended** — a combined score would itself be an invented metric, the same failure mode §2.8
already prohibits for risk composites:

1. **Trust-adjusted severity** — a CRITICAL finding on a live exposure outranks an anomaly on an
   already-SHOW_BOTH/BLOCK metric, whose ambiguity is already fully disclosed and therefore
   "less newly actionable" (the spec's words).
2. **Recency** — the evidence is one static snapshot, so recency distinguishes only what it *can*:
   a condition re-derived live from a diagnostic versus a standing register entry.
3. **Materiality** — a tiebreaker *within* a severity tier. **A missing amount sorts last within
   its tier, not as zero:** absence of a figure is not smallness.
4. **Coverage sufficiency** — an under-6-month domain is never ranked as a trend insight.

`explain_ranking()` returns all four separately, so a reviewer sees *why* one outranked another
instead of being handed a number that hides it.

---

## 4. Trust behaviour in proactive content

| Trust | Insight behaviour |
|---|---|
| SAFE | Stated with evidence |
| DISCLOSE | Stated with its caveat |
| SHOW_BOTH / BLOCK | **`headline_permitted = false`.** The insight is about the *conflict*, never asserting one competing figure as the business's position |
| NOT_DETERMINABLE | Exactly "Not determinable from exported evidence." |

An insight covering a family takes the family's **worst** trust level, not its first member's.
The AR family is the case that matters: Defs A/B are SHOW_BOTH while C/D are BLOCK, so the
family insight is BLOCK. Taking the head member's level would present a ~120× disagreement as
merely "two views to compare."

---

## 5. Delivery

The insight feed appears on the Owner Dashboard (Risks, Attention Required, Top Insights) and is
reachable conversationally. Ordering is deterministic: the same evidence produces the same feed
in the same order, every time.

---

## 6. What is never surfaced proactively

- A LOW or INFORMATIONAL finding dressed as urgent.
- An anomaly (no method exists).
- A "material" change (no threshold exists).
- A causal explanation (no experiment or control exists).
- A benchmark comparison (the evidence has only this business's records).
- A single figure for a conflicted metric.
