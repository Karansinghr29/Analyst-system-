# Owner Dashboard Implementation Specification

The Owner Executive Cockpit — what renders, in what order, under what rules.

Generated source: `dashboard_tile_registry.csv` (20 tiles) and `ui_metric_registry.csv` (49
metrics). No tile is authored by hand; every one comes from `ViewModelBuilder.owner_home()`.

---

## 1. Layout

```
┌──────────────────────────────────────────────────────────────┐
│  "How is my business doing?"        [Ask anything…]          │
│  as at the export snapshot, 2026-08-29                       │
├──────────────────────────────────────────────────────────────┤
│  BUSINESS HEALTH        8 tiles                              │
│  Revenue · Collections · Receivables* · Expenses · Profit*   │
│  Deposits · Owner payments · Cash                            │
├──────────────────────────────────────────────────────────────┤
│  OPERATIONS             8 tiles                              │
│  Occupancy* · Staying · On-notice · Booked · Move-ins ·      │
│  Move-outs · Maintenance · Electricity                       │
├──────────────────────────────────────────────────────────────┤
│  WHAT CHANGED           3 comparable measures                │
├──────────────────────────────────────────────────────────────┤
│  INSIGHTS               21 · Critical 4 · Attention 13 ·     │
│                         Conflict 4 · Positive 1              │
├──────────────────────────────────────────────────────────────┤
│  ATTENTION REQUIRED     11 owner decisions                   │
│  RECOMMENDED ACTIONS    20 grounded recommendations          │
├──────────────────────────────────────────────────────────────┤
│  RISKS 4 tiles     ·     TRUST SUMMARY across 49 metrics     │
└──────────────────────────────────────────────────────────────┘
                                    * renders no single figure
```

---

## 2. The three tiles that refuse

This is the dashboard's most important behaviour and the easiest thing to get wrong, because a
cockpit's whole idiom is one number per tile.

| Tile | Trust | Owner sees | Renders |
|---|---|---|---|
| **Receivables** `M.AR.001A` | SHOW_BOTH | "Multiple definitions — review both" | 4 labelled values + spread |
| **Profit** `M.PROFIT.001` | BLOCK | "No single reliable figure — definitions conflict" | 3 labelled values, **no chart** |
| **Occupancy** `M.OCC.001` | SHOW_BOTH | "Multiple definitions — review both" | 5 labelled values + comparison bar |

**BLOCK gets no chart at all.** SHOW_BOTH may show a side-by-side comparison bar; BLOCK may not,
because a bar chart of competing values invites the eye to pick the tallest — a soft way of
choosing the winner the trust policy forbids choosing.

The payload makes the refusal impossible to bypass: a tile with `headline_permitted=false`
carries **no `value` field at all**. There is nothing for a frontend to render as a headline.

---

## 3. Insight area

Six owner-facing categories, each mapped from conditions the insight engine already produces:

| | Category | Rule | Current |
|---|---|---|---|
| 🔴 | Critical | CRITICAL severity in the DQ register | 4 |
| 🟠 | Attention Required | HIGH severity, or a risk boundary crossed | 13 |
| 🟢 | Positive | A validated change over complete periods | 1 |
| 💡 | Opportunity | Only where evidence supports one | **0** |
| ⚠️ | Data Quality | A reliability problem | 0 |
| ⚡ | Definition Conflict | Competing definitions materially affecting reading | 4 |

**Opportunity is empty, and that is the honest state, not a rendering bug.** No opportunity is
inferred from a metric merely existing.

Severity is checked **before** trust level when categorising. Ordering it the other way buried
every CRITICAL finding under "Definition Conflict", where an owner scanning for urgent problems
would not look.

Every insight card carries: what happened · evidence · why it matters · confidence ·
recommended action · risk · what would change it.

---

## 4. "What should I focus on today?"

A prominent entry point returning the decision list: **attention items** (owner decisions no
analysis can settle) then **recommendations**, each with the seven required elements. No action
is manufactured because a metric exists.

---

## 5. What Changed

Direction and size for the three comparable monthly measures, each stating **materiality is
undefined** — no threshold exists in the evidence.

Incomplete periods are excluded and named. The export snapshot is mid-month, so 2026-08 and
2026-09 are partial; comparing a partial month against a complete one produced a spurious
"revenue fell 99.86%" during development, which is an artifact of the cut-off and not a business
event.

---

## 6. Empty and unavailable states

| Condition | Render |
|---|---|
| NOT_DETERMINABLE metric | The exact sentence + what is missing. **No chart, no zero, no placeholder** |
| Conflict with no computable figures | The conflict, stated without numbers |
| No insights in a category | The category with a count of zero and its rule — never hidden |
| Snapshot-only measure | No "Why?" affordance offered |
