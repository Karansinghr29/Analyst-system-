# Decision Support Specification

Specifies what the system produces when the owner asks *"what should I do?"*, and the conditions
under which it declines to answer that question.

---

## 1. The six required elements

Every recommendation carries all six. A recommendation missing any of them is **incomplete**, not
merely terse, and is not emitted.

| Element | Source | When it cannot be filled |
|---|---|---|
| **Evidence** | `evidence_sources` / `dq_ids` / `conflict_ids` on the insight | Never — a recommendation with no traceable evidence is not emitted at all |
| **Business impact** | `affected_amount` / `affected_count` from `data_quality_registry.csv` | Stated as "Not determinable from exported evidence." — the register records no exposure for that finding |
| **Risk** | The DQ severity and the trust level of the metrics touched | Never — severity is always recorded |
| **Confidence** | `PROVEN` / `SUSPECTED` (`data_quality_report.md`'s own `root_cause_confidence` vocabulary) | Never |
| **Recommended action** | The action itself, in recommendation register | — |
| **What would change it** | The evidence that would confirm or refute the underlying hypothesis | Stated explicitly |

Confidence is **never a numeric percentage**. `answer_contract.md` §3: no statistical calibration
of these labels exists in the evidence, so inventing a score would be inventing a measurement.

---

## 2. The BLOCK rule

The most important gate in the document set (`business_reasoning_spec.md` §2):

> "A recommendation is never emitted for a `BLOCK` metric's underlying number as if that number
> were settled — a recommendation touching a BLOCK metric must itself recommend *resolving the
> conflict* … before any operational recommendation built on a specific dollar figure can be
> made."

So for profit, tenant dues, and the other BLOCK families, the only available recommendation is:

> *Recommend an owner decision on which definition is authoritative.*

This is not a limitation to be worked around. It is the correct answer: the system cannot make a
business decision that only an owner can make, and pretending otherwise would attach a
recommendation to a figure that does not exist.

---

## 3. Ranking

`insight_generation_spec.md` §4's four dimensions, compared **lexicographically and never
blended** — a combined score would itself be an invented metric:

1. **Trust-adjusted severity** — a CRITICAL finding on a live exposure outranks an anomaly on an
   already-SHOW_BOTH/BLOCK metric, whose ambiguity is already fully disclosed and therefore
   "less newly actionable" (the spec's words).
2. **Recency** — the exported evidence is one static snapshot, so recency distinguishes only what
   it *can*: a condition re-derived live from a current diagnostic versus a standing finding
   transcribed once into the register.
3. **Materiality** — a tiebreaker *within* a severity tier. A missing amount sorts **last**
   within its tier rather than as zero: absence of a figure is not smallness.
4. **Coverage sufficiency** — an under-6-month domain is never ranked as a trend insight.

`explain_ranking()` returns all four separately, so a reviewer can see why one item outranked
another instead of being handed a number that hides it.

---

## 4. "What requires my decision?"

Returns every standing conflict whose resolution is an owner decision — the SHOW_BOTH and BLOCK
families — each with its conflict ids and the decision it needs. These are exactly the items no
amount of further analysis can settle, which is why they are surfaced separately from the
recommendations.

---

## 5. "What should I investigate first?"

Returns the ranked insight list from §3. The ordering is the ranking's, not a separate priority
judgement, so the answer to "what first?" and the answer to "what are my risks?" cannot disagree.

---

## 6. What is never produced

| Never | Reason |
|---|---|
| A recommendation without an OBSERVATION | The brief: never jump FACT → RECOMMENDATION without the intermediate chain |
| A recommendation in fact register | `business_reasoning_spec.md` §2's RECOMMENDATION gating rule |
| An unsolicited recommendation on a lookup | §3's ceiling table: a Lookup answered with a recommendation violates the spec |
| A recommendation asserting a cause | No causal evidence exists (see `analysis_workflow_spec.md` §3) |
| A recommendation for a NOT_DETERMINABLE metric | There is no finding to act on |
| A numeric confidence score | No calibration exists in the evidence |
| A materiality-based prioritisation | No threshold exists; materiality is a tiebreaker only, never a gate |

---

# Phase 7 addendum — decision support as a product surface

The sections above (Phase 6) specify the decision-support *logic* and remain unchanged. This
addendum specifies how that logic reaches the owner.

## 7. The Decision Queue

A standing, ranked list of items that require an **owner decision** — distinct from
recommendations, because no amount of further analysis can settle them.

Sourced from `conflict_disclosure_registry.csv` (12 conflicts). Each entry carries:

| Field | Content |
|---|---|
| What must be decided | Which definition is authoritative |
| Why the system cannot decide | It is a business decision, not an analytical one |
| What each option means | Every competing definition, labelled, with its own value |
| The spread | The numeric disagreement between them |
| What the decision unblocks | The metrics and answers that become single-valued |
| Evidence | Conflict ids, DQ ids, source references |

The queue does not shrink on its own. An item leaves it only when an owner decision updates the
registry's trust level — which then propagates to every surface automatically, because every
surface reads the gate rather than caching a posture.

## 8. Impact of the standing decisions

| Decision | Currently blocks |
|---|---|
| Which profit definition is authoritative | Any single profit figure; profit trend; profit-based recommendations |
| Which tenant-dues definition is authoritative | Any single receivables figure; per-tenant dues; dues-based collection targets |
| Which occupancy definition is authoritative | Any single occupancy %; occupancy trend framing |
| Which owner-rent treatment is correct | Owner-rent totals; the profit definitions that differ on it |

These four are the highest-value decisions available to the owner: each converts a permanently
multi-valued measure into a single reportable one.

## 9. Surfacing rules

- The queue appears on the Owner Dashboard under **Attention Required**.
- A conflicted metric's tile links directly to its queue entry.
- Asking *"which number is correct?"* returns the queue entry, never a number.
- A recommendation touching a queued conflict states its dependency on that decision.

## 10. What the Decision Queue must never do

| Never | Why |
|---|---|
| Suggest a default | A default is a decision made by the system |
| Rank one definition as "most likely correct" | No evidence establishes correctness |
| Expire an undecided item | An unresolved conflict does not become resolved by age |
| Let a recommendation act on a queued figure | `business_reasoning_spec.md` §2's BLOCK gating rule |
