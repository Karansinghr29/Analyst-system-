# Owner Experience Specification

The one screen the owner opens, and what happens when they touch anything on it.

**Governing requirement:** the owner opens the system and immediately sees *"how is my business
doing?"* answered — Business Health + KPIs + Changes + Risks + Insights + Why + Recommended
Actions + Evidence — without having asked.

The owner is never required to understand a metric id, a table name, SQL, a data model, analyst
terminology, BI terminology, or the trust layer. All of it is derived; all of it stays available
one click away.

---

## 1. The Owner Executive Dashboard

Sections, in the order they appear. Every metric is drawn from
`owner_dashboard_registry.csv`, generated from the live system — **no KPI is invented here.**

### 1.1 Business Health (8 tiles)

| Tile | Metric | Trust | Renders as |
|---|---|---|---|
| Revenue | `M.REV.001` | SAFE | value |
| Collections | `M.COL.001` | DISCLOSE | value + caveat |
| Receivables / tenant dues | `M.AR.001A` family | **SHOW_BOTH** | **4 definitions, no headline** |
| Expenses | `M.EXP.001` | SAFE | value |
| Profit | `M.PROFIT.001` | **BLOCK** | **conflict panel, no figure** |
| Deposits held | `M.DEP.001` | SAFE | value |
| Owner payments | `M.OWN.001` | SAFE | value |
| Cash | `M.CASH.001` | SAFE | value |

### 1.2 Operations (8 tiles)

Occupancy `M.OCC.001` (**SHOW_BOTH — 5 definitions, no headline**), staying `M.TEN.001`,
on-notice `M.TEN.002`, booked `M.TEN.003`, move-ins `M.LIFE.002`, move-outs `M.LIFE.003`,
maintenance `M.MAINT.001`, electricity `M.EB.001`.

### 1.3 Risks

Phantom deposits `M.RISK.004`, duplicate invoices `M.RISK.005`, overlapping allotments
`M.RISK.007`, ledger reconciliation `M.RISK.008` — plus the ranked insight feed (currently 20
findings).

### 1.4 Major Changes

Period-over-period movement for the comparable monthly metrics. **Each change states that
materiality is undefined**, because no threshold exists in the evidence. Incomplete periods are
excluded and named.

### 1.5 Attention Required — the Decision Queue

Every standing conflict whose resolution is an owner decision. These are the items no further
analysis can settle, which is why they are separated from recommendations.

### 1.6 Top Business Insights · Recommended Actions · Evidence & Trust Status

Ranked findings; grounded recommendations; and a trust roll-up across all 49 metrics.

---

## 2. The three tiles that refuse

This is the product's most important visual behaviour, and the easiest thing for a dashboard to
get wrong. A BI tool's native idiom is one number per tile. Three tiles must resist it:

> **Profit** — no figure. The panel reads: *three incompatible definitions of profit exist in
> this system; they differ by ~36.6% on owner-rent treatment alone. Choosing one is a business
> decision.* Each definition's own value is listed, labelled. The owner decision is surfaced.

> **Receivables** — four definitions spanning roughly two orders of magnitude. All four shown.

> **Occupancy** — five definitions. All shown, with the spread.

A tile that renders `definitions[0]` as "the" number has violated the contract.
`validate_card()` catches exactly that.

---

## 3. Click behaviour

Every element is a conversation entry point. Context carries; nothing is re-derived differently.

| Owner clicks | System does |
|---|---|
| **Why?** on a change | Driver analysis over documented dependency edges — patterns, never causes |
| **Drill down** on a tile | Grouped lookup on a dimension the metric's grain supports |
| **What should I do?** on an insight | Its recommendation, with evidence, impact, confidence, and what would change it |
| **How was this calculated?** | Calculation provenance + evidence chain + validation status |
| **Which number is correct?** on a conflict | Every competing definition + *"this is an owner decision, not an analytical one"* |

---

## 4. What the owner sees when the answer is "we can't say"

The product's credibility rests on these being visible rather than hidden:

- **A conflict** → all definitions, the spread, and the decision needed. Never a default.
- **A missing metric** → *"Not determinable from exported evidence."* plus what specifically is
  missing. Never an estimate, never a zero.
- **An unsupported framing** (a rate, a benchmark, a property comparison) → what the evidence
  does contain, and why the requested shape is not available.
- **A change** → direction and size, with materiality explicitly undefined.

---

## 5. Progressive disclosure

Four levels, each one click from the last:

```
1. the figure            "Revenue: ₹72,705,593.43"
2. its qualification     validation MATCH · confidence HIGH · caveats · conflicts
3. its derivation        filters · aggregation · reversal & soft-delete policy · as-of basis
4. its evidence          manifest keys · source CSVs · the validation check that confirmed it
```

Level 1 is what the owner sees by default. Levels 2–4 are never *removed* — they are one
interaction away, and `explainability.py` guarantees the chain exists for every answer.
