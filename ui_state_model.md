# UI State Model

Every state the interface can be in, and the states it must never conflate.

---

## 1. The six terminal states

These look similar and mean different things. Rendering any two identically is a correctness
failure, not a styling shortcut.

| State | Meaning | Signal | Owner copy |
|---|---|---|---|
| **Loading** | request in flight | client-side | skeleton |
| **No data** | the query ran, the result is empty | value present, empty/zero | "No records in this period." |
| **No evidence** | the source file is absent | `unavailable_reason` names the file | "The source records are not in the export." |
| **Not determinable** | the evidence cannot support it | exact phrase present | *Not determinable from exported evidence.* + what is missing |
| **Blocked** | definitions conflict | `headline_permitted=false` + `definitions[]` | "No single reliable figure — definitions conflict" |
| **System error** | the engine failed | error envelope, no value | "Something went wrong. No figure is shown." |

The pair that matters most is **No data** versus **Not determinable**. A measured zero and an
unmeasurable quantity are opposite facts; a UI that shows both as "0" or both as "—" tells the
owner something false in one of the two cases.

---

## 2. Calculation and validation states

| State | Rendered |
|---|---|
| Computed, validated MATCH | value + "Verified" |
| Computed, validated DIFFERS | value + the documented mechanism, never presented as fresh |
| Computed, unverified | value + "not independently re-validated" |
| Sanity check failed | **no value at all** — the engine halts rather than emitting it |

The last is deliberate: `analytics_execution_spec.md` §8 requires a halt, because a failed sanity
check indicates an engine bug, not a business fact.

---

## 3. Snapshot warnings

Persistent, not dismissible:

- **As-of** — the export snapshot, 2026-08-29
- **Incomplete periods** — 2026-08 and 2026-09 are partial and excluded from comparisons, named
  wherever a comparison appears
- **Coverage** — per domain, since maintenance (20 months) and EB (1–5 months) cannot support
  the trend framing the other domains can

---

## 4. Partial data

When some parts of a view resolve and others do not, the resolved parts render and the
unresolved ones carry their own state. A view is never suppressed wholesale because one tile
failed — that would hide 19 good tiles to hide one bad one.

Partial family coverage is disclosed: when some competing definitions can answer a period and
others cannot, the excluded ones are **named**, not silently dropped.

---

## 5. Conversation states

| State | Behaviour |
|---|---|
| Idle | suggestions shown |
| Thinking | request in flight |
| Answered | full answer panel |
| Clarification required | question + options; nothing executed |
| Clarification still ambiguous | re-ask; the clarification stays open |
| Clarification rejected | explain why the system cannot choose; still nothing executed |
| Refused | the reason, with the exact phrase where applicable |

An unanswered clarification never advances to an answer. Repetition is not consent.

---

## 6. State transitions that are forbidden

| Forbidden transition | Why |
|---|---|
| Blocked → showing a value | Requires an explicit owner definition selection |
| Not determinable → estimate | No estimate exists to show |
| Clarification → answer without a reply | An unanswered clarification is not permission |
| Any state → a frontend-computed value | The UI has no calculation path |
| Error → last known value | A stale figure presented as current is worse than none |
