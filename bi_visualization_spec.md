# BI Visualization Specification

Which visual each metric may carry, and — more importantly — which it must not.

Generated source: `visualization_registry.csv`, one row per metric, listing the permitted widget,
the permitted chart, and the **forbidden visuals** for that trust level.

---

## 1. Trust controls visualization

| Trust | Widget | Chart | Forbidden |
|---|---|---|---|
| SAFE | `kpi_card` | line, where a series exists | — |
| DISCLOSE | `kpi_card_with_caveat` | line, where a series exists | — |
| SHOW_BOTH | `multi_definition_panel` | multi-definition comparison bar | kpi_card, single_value, line, gauge, sparkline |
| BLOCK | `conflict_panel_no_headline` | **none** | all of the above **plus** multi_definition_bar |
| NOT_DETERMINABLE | `not_determinable_notice` | **none** | all of the above plus zero_placeholder |

The prohibitions are expressed as prohibitions, not as an absence of permissions, because the
failure mode is a UI rendering something it was never told not to.

---

## 2. Why BLOCK forbids even the comparison bar

SHOW_BOTH says "here are several valid readings; compare them" — a side-by-side bar serves that.

BLOCK says "these disagree materially and no single figure may be stated." A bar chart of the
competing values still invites the eye to pick the tallest, which is choosing a winner by visual
means rather than by argument. So BLOCK renders a conflict **panel**: labelled values in text,
the spread stated, the decision surfaced.

---

## 3. A chart is offered only where a series exists

Currently 3 metrics carry month-keyed series (`M.REV.002`, `M.PNL.001`, `M.COL.002`). Every other
metric gets `chart_type: none` with a stated reason:

- competing definitions — a single series would pick one
- no exported reference exists — *Not determinable from exported evidence.*
- no month-keyed series exists for this metric

Offering a chart otherwise means plotting something the evidence does not contain.

---

## 4. Supported interactions

KPI cards · line charts · bar charts · stacked breakdowns · period comparisons · trend tables ·
detail tables · filters · date selectors · drill-down · drill-through · cross-filtering ·
sorting · ranking · export · metric definition panel · evidence panel · data-quality panel.

Each is trust-gated. A breakdown is offered only on a dimension the documented grain supports;
the degenerate dimensions (organization, property — one distinct value each) are excluded, since
a drilldown on them yields a single row that looks like a comparison.

---

## 5. Never visualised

| Never | Why |
|---|---|
| A single profit / dues / occupancy KPI | Competing definitions |
| Any chart for a NOT_DETERMINABLE metric | Nothing to plot; a zero would be a false claim |
| A property comparison | One property exists |
| Maintenance or EB year-on-year | 20 months and 1–5 months of coverage |
| A threshold-coloured change indicator | No materiality threshold exists |
| An anomaly marker | No statistical method is specified |
| A benchmark line | The evidence holds only this business own records |

---

## 6. Cross-filtering safety

Two guards. **Grain compatibility:** a filter propagates only to metrics whose grain supports the
dimension. **No cross-family arithmetic:** selecting revenue and expenses does not yield "profit"
— that combination resolves to `M.PROFIT.001`, which is BLOCK, and the combination guard in the
trust gate refuses it.
