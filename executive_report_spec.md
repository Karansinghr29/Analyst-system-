# Executive Report Specification

The generated management report. Built entirely from `ExecutiveSummaryBuilder` and the view
models.

**Phase 8 brief 9:** "The report must be generated from the same engine outputs. Never maintain
a separate hardcoded KPI calculation for the report."

A report with its own calculations is a report that drifts from the dashboard, and the drift is
invisible until someone compares two numbers that should have matched.

---

## 1. Structure

| Section | Source |
|---|---|
| Executive Summary | business health tiles + insight counts |
| Business Health | the 8 Business Health tiles |
| Financial Performance | revenue · expenses · profit · collections · receivables · cash |
| Operations | occupancy · tenant lifecycle · maintenance · EB |
| Customers / Tenants | staying · on-notice · booked · move-ins · move-outs |
| Risks | ranked insight feed |
| Data Quality | the DQ register by severity |
| What Changed | comparable period changes, materiality undefined |
| Why | driver analysis for each detected change |
| Recommended Actions | grounded recommendations |
| Definition Conflicts | the 12 conflicted metrics, each with all definitions |
| Evidence / Methodology | manifest keys · validation references · coverage |

---

## 2. Trust rendering in a document

A printed report cannot offer a click, so every qualification must be **on the page**:

| Trust | In the report |
|---|---|
| SAFE | Figure with its validation status |
| DISCLOSE | Figure with the caveat printed beneath it — not a footnote marker |
| SHOW_BOTH | Every definition in a labelled table, plus the spread |
| BLOCK | No figure. The conflict, each definition, the decision required |
| NOT_DETERMINABLE | *Not determinable from exported evidence.* plus what is missing |

The Financial Performance section therefore contains **no profit figure**. It contains a profit
*section* explaining that three definitions exist, listing each, and naming the decision needed.

A report that printed one profit number would be more comfortable to read and less true.

---

## 3. Methodology section

Every report closes with:

- **Coverage** — ledger ~54 months, occupancy 67, maintenance 20, EB 1–5
- **As-of basis** — the export snapshot, 2026-08-29, and which periods were excluded as
  incomplete
- **Validation** — 80 checks, 70 MATCH, 4 documented DIFFERS with mechanisms, 20 unverified
- **Limitations** — materiality undefined · anomaly detection unavailable · no causal claims ·
  no benchmarks · single property
- **Evidence** — the manifest keys underlying each figure

This section is not boilerplate. It is what lets a reader who was not in the room evaluate the
numbers rather than trust them.

---

## 4. What the report never contains

| Never | Why |
|---|---|
| A profit, dues, or occupancy headline | Competing definitions |
| A materiality judgement | No threshold exists |
| A causal explanation | No experiment or control exists |
| A benchmark comparison | Only this business records exist |
| A recomputed KPI | The report reads engine output, never its own arithmetic |
| A hidden caveat | A caveat behind a marker is a caveat the reader may miss |

---

## 5. Determinism

The same evidence produces the same report. Two runs are byte-comparable apart from the
generation timestamp, which is what allows a reader to diff this month against last.
