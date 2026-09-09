# BI Dashboard Specification

A Power BI-style analytical experience over the semantic layer — with one structural difference
from a conventional BI tool, which this document exists to specify.

**The difference:** a BI tool's native idiom is *one number per tile*. Three of this business's
most important measures — profit, tenant dues, occupancy — cannot honestly be rendered that way.
So the dashboard contract makes the refusal **machine-readable** rather than leaving it to a
report author's discretion.

---

## 1. The card contract

Every metric exposes the full payload in `engine/bi_contract.py` (**49/49 cards valid**):

```
metric_id · display_name · definition · value · unit · period · dimensions · filters ·
trust_level · confidence · evidence · conflicts · dq_issues · calculation_trace ·
comparison · insight · recommendation
```

plus the fields that govern rendering:

```
headline_permitted · definitions[] · render_directive · caveat · validation_status · limitations
```

`headline_permitted = false` means **the tile must not render a single value.** A dashboard that
ignores it and renders `definitions[0]` has violated the contract — and `validate_card()` detects
exactly that, so the violation is caught in CI rather than discovered by an owner reading a wrong
number off a tile.

---

## 2. Render directives

| Directive | When | Widget behaviour |
|---|---|---|
| `render_single_value` | SAFE | Number, unit, validation status |
| `render_single_value` + caveat | DISCLOSE | Number **with** the caveat rendered beside it — not behind a tooltip |
| `render_all_definitions_labelled` | SHOW_BOTH | Every definition, labelled, plus the spread. No default, no average, no "primary" |
| `render_conflict_explanation_no_headline` | BLOCK | No figure. Explanation, each definition, named conflicts, the owner decision |
| `render_not_determinable_text` | NOT_DETERMINABLE | Exactly "Not determinable from exported evidence." + what is missing. **No chart, no placeholder, no zero** |

The last row matters: a zero-valued chart for a NOT_DETERMINABLE metric reads as "we measured it
and it was nothing," which is false. Absence of evidence is rendered as absence, not as zero.

---

## 3. Supported interactions

| Feature | Supported | Constraint |
|---|---|---|
| KPI cards | yes | Trust-gated per §2 |
| Trend charts | yes | Only for metrics with a monthly series; incomplete periods excluded and named |
| Period comparison | yes | Both periods identically defined; **materiality undefined** |
| Breakdowns | yes | Only on dimensions the metric's documented grain supports |
| Filters | yes | Only over `business_dimensions.md` entries |
| Drill-down | yes | Grain-checked; an unsupported grain is refused, not approximated |
| Drill-through to records | yes | To manifest-resolved source rows |
| Cross-filtering | yes | Within a grain; **never across incompatible definitions** |
| Metric definitions | yes | Surfaced from the registry verbatim |
| Source/evidence view | yes | Manifest keys → exported CSV → validation check |
| Trust / conflict / DQ indicators | yes | Required on every card, not optional |
| Export & reporting | yes | Exports carry trust and conflict columns |
| Management summary | yes | The 7-section briefing |

---

## 4. What must never be visualised

| Never | Why |
|---|---|
| A single profit / dues / occupancy KPI | Competing definitions; a tile would silently pick one |
| A chart for a NOT_DETERMINABLE metric | There is nothing to plot; a zero would be a false statement |
| A property-comparison chart | One property exists — the visual would imply a ranking that does not exist |
| A trend for maintenance or EB beyond coverage | 20 months and 1–5 months respectively; a YoY line would be fabricated |
| A materiality-coloured change indicator (red/green by threshold) | The threshold does not exist |
| An anomaly marker | No statistical method is specified |
| A benchmark line | The evidence contains only this business's own records |

---

## 5. Cross-filtering safety

Cross-filtering is where a BI tool most easily produces a number nobody defined. Two guards:

1. **Grain compatibility** — a filter may only propagate to metrics whose documented grain
   supports the dimension.
2. **No cross-family arithmetic** — the gate's combination guard refuses composites whose
   components are competing definitions of one concept, *and* refuses any composite whose
   documented covering metric is itself conflicted. Selecting revenue and expenses does not
   produce "profit": that combination resolves to `M.PROFIT.001`, which is BLOCK.

---

## 6. Drill path

```
KPI card
  → trend (if a series exists)
    → period comparison (complete periods only)
      → breakdown by a supported dimension
        → detail table
          → source records (manifest-resolved)
            → the validation check that confirmed the reconstruction
```

Trust, conflicts and DQ indicators travel down **every** level. A drill-down never sheds the
caveat that applied at the top.
