# Business Question Matrix

**Generated** by `scripts/build_question_matrix.py`, which runs every question through
the live Phase 1–6 system. This records what the product *does*, not what it intends.

Columns: the intent resolved, the analyst lenses routed, the metrics answered, the trust
posture, the shape of the answer, and how far up the reasoning ladder the answer climbs.

Every `metric_id` below already exists in `semantic_metric_registry.csv`. No definition
is invented here.

---

## Trust behaviour (applies to every row)

| Trust level | Answer behaviour |
|---|---|
| `SAFE` | Answer normally, with evidence and validation status. |
| `DISCLOSE` | Answer, with the documented caveat carried alongside the figure. |
| `SHOW_BOTH` | Present every competing definition and the spread. Never select one. |
| `BLOCK` | No headline figure. Explain why, list each definition, surface the owner decision. |
| `NOT_DETERMINABLE` | State exactly: "Not determinable from exported evidence." |

---

## Matrix

| Question | Intent | Analyst lenses | Metrics | Trust | Answer shape | Ladder |
|---|---|---|---|---|---|---|
| How is the business doing? | briefing | management_reporting_analyst, business_analyst, risk_dq_analyst | `M.REV.001, M.COL.001, M.AR.001A, M.EXP.001` | — | Management briefing | — |
| What changed? | what_changed | data_scientist, management_reporting_analyst, bi_analyst | `M.REV.002, M.PNL.001, M.COL.002` | — | Period-change list | — |
| Why did profit fall? | driver | financial_analyst, data_scientist, business_analyst | `M.PROFIT.001` | BLOCK | 3 competing definitions, no headline | FACT→CALC→OBS→INF→HYP |
| Why are collections down? | driver | data_scientist, business_analyst | `—` | — | Clarification (never guessed) | — |
| Which area needs attention? | what_to_do | decision_support_analyst, business_analyst, risk_dq_analyst | `—` | — | Decision list | — |
| What are the biggest risks? | risk_scan | risk_dq_analyst, business_analyst | `M.RISK.002, M.RISK.003, M.RISK.004, M.RISK.005` | DISCLOSE | Single value | FACT→CALCULATION |
| What should I do today? | what_to_do | decision_support_analyst, business_analyst, risk_dq_analyst | `—` | — | Decision list | — |
| What should I fix first? | what_to_do | decision_support_analyst, business_analyst, risk_dq_analyst | `—` | — | Decision list | — |
| Where am I losing money? | risk_scan | risk_dq_analyst, business_analyst | `M.RISK.002, M.RISK.003, M.RISK.004, M.RISK.005` | DISCLOSE | Single value | FACT→CALCULATION |
| Which tenants need attention? | risk_scan | risk_dq_analyst, business_analyst | `M.RISK.002, M.RISK.003, M.RISK.004, M.RISK.005` | DISCLOSE | Single value | FACT→CALCULATION |
| Are expenses increasing? | lookup | financial_analyst, data_analyst | `M.EXP.001` | SAFE | Single value | FACT→CALCULATION |
| What caused this change? | driver | data_scientist, business_analyst | `—` | — | Clarification (never guessed) | — |
| Show me the important business insights. | briefing | management_reporting_analyst, business_analyst, risk_dq_analyst | `M.REV.001, M.COL.001, M.AR.001A, M.EXP.001` | — | Management briefing | — |
| Give me the management report. | briefing | management_reporting_analyst, business_analyst, risk_dq_analyst | `M.REV.001, M.COL.001, M.AR.001A, M.EXP.001` | — | Management briefing | — |
| Compare this month with last month. | what_changed | data_scientist, management_reporting_analyst, bi_analyst | `M.REV.002, M.PNL.001, M.COL.002` | — | Period-change list | — |
| What should I tell the owner? | briefing | management_reporting_analyst, business_analyst, risk_dq_analyst | `M.REV.001, M.COL.001, M.AR.001A, M.EXP.001` | — | Management briefing | — |
| Is there anything unusual? | anomaly | data_scientist, data_analyst | `—` | — | Clarification (never guessed) | — |
| Can I trust this number? | what_to_trust | risk_dq_analyst, data_analyst | `M.REV.001, M.REV.002, M.COL.001, M.COL.002` | — | Trust posture list | — |
| How much revenue did we make? | lookup | financial_analyst, data_analyst | `M.REV.001` | SAFE | Single value | FACT→CALCULATION |
| What is occupancy? | lookup | operations_analyst, data_analyst, risk_dq_analyst | `M.OCC.001` | SHOW_BOTH | 5 competing definitions, no headline | FACT→CALCULATION |
| How much do tenants owe? | lookup | financial_analyst, data_analyst, risk_dq_analyst | `M.AR.001A, M.AR.001B, M.AR.001C, M.AR.001D` | SHOW_BOTH | 4 competing definitions, no headline | FACT→CALCULATION |
| How much deposit is held? | lookup | financial_analyst, data_analyst | `M.DEP.001` | SAFE | Single value | FACT→CALCULATION |
| What was our electricity cost? | lookup | operations_analyst, data_analyst, risk_dq_analyst | `M.EB.001` | DISCLOSE | Single value | FACT→CALCULATION |
| How many maintenance tickets were raised? | lookup | operations_analyst, data_analyst | `M.MAINT.001` | SAFE | Single value | FACT→CALCULATION |
| Which property is performing better? | comparison | data_analyst, bi_analyst, business_analyst | `—` | — | Refusal with stated reason | — |

---

## Stated limitations

- **How is the business doing?** — Materiality is undefined for every change: no threshold exists in the exported evidence or in any specification (insight_generation_spec.md 2 condition 3). Two of the four document
- **What changed?** — Materiality is undefined for every change: no threshold exists in the exported evidence (insight_generation_spec.md 2 condition 3).
- **Why did profit fall?** — M.PROFIT.001 is BLOCK: the decomposition is presented per definition and is never merged into a single explanation (analytics_execution_spec.md 2.6). Conflicting definitions exist.
- **Which area needs attention?** — Materiality is undefined for every change: no threshold exists in the exported evidence or in any specification (insight_generation_spec.md 2 condition 3). Two of the four document
- **What should I do today?** — Materiality is undefined for every change: no threshold exists in the exported evidence or in any specification (insight_generation_spec.md 2 condition 3). Two of the four document
- **What should I fix first?** — Materiality is undefined for every change: no threshold exists in the exported evidence or in any specification (insight_generation_spec.md 2 condition 3). Two of the four document
- **Show me the important business insights.** — Materiality is undefined for every change: no threshold exists in the exported evidence or in any specification (insight_generation_spec.md 2 condition 3). Two of the four document
- **Give me the management report.** — Materiality is undefined for every change: no threshold exists in the exported evidence or in any specification (insight_generation_spec.md 2 condition 3). Two of the four document
- **Compare this month with last month.** — Materiality is undefined for every change: no threshold exists in the exported evidence (insight_generation_spec.md 2 condition 3).
- **What should I tell the owner?** — Materiality is undefined for every change: no threshold exists in the exported evidence or in any specification (insight_generation_spec.md 2 condition 3). Two of the four document
- **Can I trust this number?** — Trust levels are the semantic layer's own, unchanged by this layer.
- **Which property is performing better?** — The question asks for a comparison the exported data's structure cannot support; this is a fact about the data, not a calculation failure.

---

## Coverage

| Answer shape | Count |
|---|---|
| Single value | 8 |
| Management briefing | 4 |
| Clarification (never guessed) | 3 |
| Decision list | 3 |
| Period-change list | 2 |
| 3 competing definitions, no headline | 1 |
| Trust posture list | 1 |
| 5 competing definitions, no headline | 1 |
| 4 competing definitions, no headline | 1 |
| Refusal with stated reason | 1 |

**25 questions catalogued.** Every one either answers, asks for
clarification, or refuses with a stated reason. None guesses.

