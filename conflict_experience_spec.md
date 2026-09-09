# Conflict Experience Specification

The dedicated view for a metric whose definitions disagree. Built by
`ViewModelBuilder.conflict_view()`. Generated source: `conflict_disclosure_registry.csv`
(12 conflicted metrics).

**The system never chooses a winner.** Not by default, not by ordering, not by rendering one
larger, and not by putting one first and calling it primary.

---

## 1. Layout

```
Tenant Receivables                                       M.AR.001A–D
⚠  Multiple definitions detected                     [Definitions differ]

More than one evidence-backed definition exists and they give different
answers. All are shown; choosing between them is a business decision.

┌────────────────────────────────────────────────────────────────────┐
│ Def A — v_outstanding_receivables (reversals excluded)             │
│ ₹83,297.85                                                          │
│ SOURCE     F.006 · T.journal_lines · T.journal_entries             │
│ TIME       entry_date basis (ledger span)                          │
│ CALC       reversal-excluded ledger AR balance                     │
│ TRUST      Multiple definitions — review both                      │
│ VALIDATION MATCH (AR.01)                                            │
├────────────────────────────────────────────────────────────────────┤
│ Def B — v_tenant_current_dues (reversals included)                 │
│ ar_balance ₹83,297.85 · deposit_held ₹4,221,150.00                 │
│ …                                                                   │
├────────────────────────────────────────────────────────────────────┤
│ Def C — application tenant_allotments.balance_due                  │
│ ₹1,009,125.78                                                       │
├────────────────────────────────────────────────────────────────────┤
│ Def D — tenant_transactions (frozen legacy ledger)                 │
│ unclipped ₹9,968,023.32 · floored ₹10,517,031.27                   │
└────────────────────────────────────────────────────────────────────┘

SPREAD       Def A vs Def D differ by roughly two orders of magnitude
CONFLICTS    C.001 · C.003 · C.005      DQ  DQ.002 · DQ.019 · DQ.023
DECISION     Requires an owner decision on which definition is authoritative
```

---

## 2. Per-definition fields

Each definition carries: **value · source · time semantics · calculation · trust ·
validation status · limitations.** Every one comes from the engine result for that definition;
none is summarised or inferred.

---

## 3. "Which definition should we use?"

The answer is deliberately not a number:

> This requires a business decision, not an analytical one. Each definition is evidence-backed
> and internally consistent; they disagree because they measure different things. The system will
> not choose between them, and will keep showing all of them until an owner decision records
> which is authoritative.

The panel then states what deciding would unblock — which is the useful part: the four standing
decisions (profit, tenant dues, occupancy, owner-rent treatment) each convert a permanently
multi-valued measure into a single reportable one.

---

## 4. Presentation rules

| Rule | Reason |
|---|---|
| No definition is listed first as "primary" | Ordering implies precedence |
| No definition is styled more prominently | Visual weight is a soft endorsement |
| No average, midpoint, or range is shown | A synthesised number is a new invented metric |
| BLOCK renders no chart at all | A bar chart invites picking the tallest |
| SHOW_BOTH may render a comparison bar | Comparison is the point; no single value is implied |
| The spread is stated in words | "Roughly two orders of magnitude" is the finding |

---

## 5. When the definitions cannot be computed

`M.OCC.005` (historical day-weighted occupancy) carries a real conflict whose figures are not
computable in the current engine. The panel shows the **conflict without figures**, and says so:

> The competing definitions of this measure are not computable in the current engine, so the
> conflict is shown without figures rather than implying two comparable numbers exist.
> *Not determinable from exported evidence.*

Hiding the metric entirely would tell the owner no conflict exists. Showing invented figures
would be worse. Showing the conflict without numbers is the only honest option.

---

## 6. Where conflicts must appear

Every conflicted metric must surface on **all** of: owner dashboard · role views · BI cards ·
executive summary · insight feed · decision queue · conversational answers. The validator checks
each surface, because a conflict dropped from one of them is a conflict the owner may never see.
