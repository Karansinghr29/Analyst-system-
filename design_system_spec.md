# Design System Specification

The visual language. Its main job is to make trust legible without making the interface feel
like a compliance tool.

---

## 1. Trust visual language

Five states, each with an owner-facing label and a machine state that travels in the DOM.

| Trust | Owner label | Badge | Tone | Icon |
|---|---|---|---|---|
| SAFE | Reliable | Verified | neutral | check |
| DISCLOSE | Usable, with a caveat | Caveat applies | caution | info |
| SHOW_BOTH | Multiple definitions — review both | Definitions differ | conflict | split |
| BLOCK | No single reliable figure — definitions conflict | Conflict | conflict | alert |
| NOT_DETERMINABLE | Cannot be determined from the available evidence | Unavailable | unavailable | minus |

**Both halves are required.** The owner reads the label; the element still carries
`data-trust="BLOCK"`. Every downstream check — validator, tests, render directives — reads the
machine state, never the label, so translation can never weaken enforcement.

---

## 2. Tone, not alarm

`conflict` tone must read as *"this needs your judgement"*, not as an error. A definition
conflict is not a malfunction — it is an accurate report that the business has two valid ways of
counting something. Styling it as a failure would push owners to dismiss it.

`unavailable` must read as neutral absence, not as a broken tile. The most likely
misinterpretation of a NOT_DETERMINABLE state is "the system is broken"; the second most likely
is "the value is zero". Both are wrong, and the copy carries the distinction.

---

## 3. Prominence

```
BLOCK (4) > SHOW_BOTH (3) > NOT_DETERMINABLE (2) > DISCLOSE (1) > SAFE (0)
```

A conflict the owner cannot see is a conflict that does not exist for them, so conflicted tiles
are the most visually prominent — the inverse of the usual dashboard instinct to foreground the
tidy numbers.

---

## 4. Caveats are never hidden

A DISCLOSE caveat renders **beside** the number, in the same visual block. Never a tooltip, never
a footnote marker, never an expandable the owner may not open. The rule from the answer contract
holds in the UI: *"must not remove important caveats just to make the answer shorter."*

---

## 5. Number formatting

All formatting is server-side (`format_value`). The UI renders `display_value` as given.

A UI that formats is a UI that can round, truncate, or unit-convert a figure away from what the
engine computed — and the divergence would be invisible, because both sides would look correct.

---

## 6. Empty and unavailable states

| State | Visual | Copy |
|---|---|---|
| Loading | skeleton | — |
| No data | empty state | "No records in this period." |
| No evidence | unavailable | "The source records for this are not in the export." |
| Not determinable | unavailable | *Not determinable from exported evidence.* + what is missing |
| Blocked | conflict panel | "No single reliable figure — definitions conflict" |
| System error | error | "Something went wrong. No figure is shown." |

Six distinct states. Collapsing any two is a correctness failure: "no data" and "not
determinable" rendered identically would tell the owner a measured zero where the truth is an
unmeasurable quantity.

---

## 7. Accessibility

- Trust is never conveyed by colour alone — badge text and icon carry it.
- Conflict panels are navigable by keyboard; each definition is a focusable region.
- `aria-label` on every tile includes the trust label, so a screen reader hears
  "Profit — no single reliable figure, definitions conflict" rather than a number.
- Charts carry a text alternative built from the same payload.
- Contrast meets WCAG AA in both light and dark.

---

## 8. Responsive behaviour

| Breakpoint | Layout |
|---|---|
| Desktop | full cockpit; conflicts expanded |
| Tablet | sections stack; conflicts expanded |
| Mobile | one column; conflicts **still expanded** |

Conflicts are never collapsed to save space. Space pressure is exactly when the temptation to
show one number appears, and it is exactly when doing so would be most misleading.
