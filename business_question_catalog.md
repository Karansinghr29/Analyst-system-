# Business Question Catalog

**Generated** by `scripts/build_question_catalog.py`, which runs every question through
the real system. This records what the system *does*, not what it was intended to do.

For each question: the intent it resolves to, the analyst lenses routed, the metrics
answered, the trust posture, the shape of the answer, and whether a recommendation is
eligible. Where the registry cannot answer, the entry says so with the exact phrase
**"Not determinable from exported evidence."**

No definition is invented here. Every `metric_id` below already exists in
`semantic_metric_registry.csv`.

---

## Coverage summary

| Outcome | Count |
|---|---|
| Questions catalogued | 30 |
| Answered with a single value | 13 |
| Answered with competing definitions (no headline) | 6 |
| Routed to a whole-business workflow | 6 |
| Clarification required (never guessed) | 3 |
| Refused with a stated reason | 2 |

---

## Catalog

| Question | Area | Intent | Analyst lenses | Metrics | Trust | Answer shape | Rec. eligible |
|---|---|---|---|---|---|---|---|
| What is today's occupancy? | Occupancy | lookup | operations_analyst, data_analyst, risk_dq_analyst | `M.OCC.001` | SHOW_BOTH | All 5 competing definitions, no headline | no |
| How many tenants are staying? | Tenant lifecycle | lookup | operations_analyst, data_analyst | `M.TEN.001` | SAFE | Single value | no |
| How many are on notice? | Tenant lifecycle | lookup | operations_analyst, data_analyst | `M.TEN.002` | SAFE | Single value | no |
| What is revenue this month? | Revenue | lookup | financial_analyst, data_analyst | `M.REV.001` | SAFE | Single value | no |
| How much did we collect? | Collections | lookup | data_analyst | `—` | — | Clarification request | no |
| How much do tenants owe? | Receivables | lookup | financial_analyst, data_analyst, risk_dq_analyst | `M.AR.001A, M.AR.001B, M.AR.001C, M.AR.001D` | SHOW_BOTH | All 4 competing definitions, no headline | no |
| Which tenants have outstanding dues? | Receivables | lookup | financial_analyst, data_analyst, risk_dq_analyst | `M.AR.001A, M.AR.001B, M.AR.001C, M.AR.001D` | SHOW_BOTH | All 4 competing definitions, no headline | no |
| Why did collections fall? | Collections | driver | data_scientist, business_analyst | `—` | — | Clarification request | no |
| Why did profit fall? | Profit | driver | financial_analyst, data_scientist, business_analyst | `M.PROFIT.001` | BLOCK | All 3 competing definitions, no headline | no |
| Which expense category is largest? | Expenses | lookup | financial_analyst, data_analyst | `M.EXP.001` | SAFE | Single value | no |
| How much owner payment was made? | Owner payments | lookup | financial_analyst, data_analyst | `M.OWN.001` | SAFE | Single value | no |
| How much deposit is held? | Deposits | lookup | financial_analyst, data_analyst | `M.DEP.001` | SAFE | Single value | no |
| How many deposits are unresolved? | Deposits | lookup | financial_analyst, data_analyst | `M.DEP.001` | SAFE | Single value | no |
| Which apartments are under-utilized? | Occupancy | lookup | data_analyst | `—` | — | Refusal with reason | no |
| Which property is performing better? | Cross-domain | comparison | data_analyst, bi_analyst, business_analyst | `—` | — | Refusal with reason | no |
| Which month had the highest revenue? | Revenue | lookup | financial_analyst, data_analyst | `M.REV.001` | SAFE | Single value | no |
| Which month had the highest profit? | Profit | lookup | financial_analyst, data_analyst, risk_dq_analyst | `M.PROFIT.001` | BLOCK | All 3 competing definitions, no headline | no |
| What are our biggest financial risks? | Risk | risk_scan | risk_dq_analyst, business_analyst | `M.RISK.002, M.RISK.003, M.RISK.004, M.RISK.005` | DISCLOSE | Single value | no |
| What data problems should I know about? | Data quality | what_to_trust | risk_dq_analyst, data_analyst | `M.REV.001, M.REV.002, M.COL.001, M.COL.002` | — | Trust posture list | no |
| Which numbers should I trust? | Data quality | what_to_trust | risk_dq_analyst, data_analyst | `M.REV.001, M.REV.002, M.COL.001, M.COL.002` | — | Trust posture list | no |
| What changed this month? | Cross-domain | what_changed | data_scientist, management_reporting_analyst, bi_analyst | `M.REV.002, M.PNL.001, M.COL.002` | — | Period-change list | no |
| What requires my decision? | Decision support | what_to_do | decision_support_analyst, business_analyst, risk_dq_analyst | `—` | — | Decision list | yes |
| What should I investigate first? | Decision support | what_to_do | decision_support_analyst, business_analyst, risk_dq_analyst | `—` | — | Decision list | yes |
| How many maintenance tickets were raised? | Maintenance | lookup | operations_analyst, data_analyst | `M.MAINT.001` | SAFE | Single value | no |
| What was our electricity cost? | EB / electricity | lookup | operations_analyst, data_analyst, risk_dq_analyst | `M.EB.001` | DISCLOSE | Single value | no |
| Does the trial balance balance? | Accounting | lookup | financial_analyst, data_analyst | `M.TB.001` | SAFE | Single value | no |
| How much cash do we have? | Cash | lookup | financial_analyst, data_analyst | `M.CASH.001` | SAFE | Single value | no |
| Why are dues increasing? | Receivables | driver | financial_analyst, data_scientist, business_analyst | `M.AR.001A, M.AR.001B, M.AR.001C, M.AR.001D` | — | Clarification request | no |
| Why is occupancy low? | Occupancy | driver | operations_analyst, data_scientist, business_analyst | `M.OCC.001` | SHOW_BOTH | All 5 competing definitions, no headline | no |
| How is the business doing? | Cross-domain | briefing | management_reporting_analyst, business_analyst, risk_dq_analyst | `M.REV.001, M.COL.001, M.AR.001A, M.EXP.001` | — | Management briefing | no |

---

## Stated limitations

- **Why did profit fall?** — M.PROFIT.001 is BLOCK: the decomposition is presented per definition and is never merged into a single explanation (analytics_execution_spec.md 2.6). Conflicting definitions exist.
- **Which property is performing better?** — The question asks for a comparison the exported data's structure cannot support; this is a fact about the data, not a calculation failure.
- **What data problems should I know about?** — Trust levels are the semantic layer's own, unchanged by this layer.
- **Which numbers should I trust?** — Trust levels are the semantic layer's own, unchanged by this layer.
- **What changed this month?** — Materiality is undefined for every change: no threshold exists in the exported evidence (insight_generation_spec.md 2 condition 3).
- **What requires my decision?** — Materiality is undefined for every change: no threshold exists in the exported evidence or in any specification (insight_generation_spec.md 2 condition 3). Two of the four documented insight triggers 
- **What should I investigate first?** — Materiality is undefined for every change: no threshold exists in the exported evidence or in any specification (insight_generation_spec.md 2 condition 3). Two of the four documented insight triggers 
- **Why are dues increasing?** — M.AR.001A is SHOW_BOTH: the decomposition is presented per definition and is never merged into a single explanation (analytics_execution_spec.md 2.6). Conflicting definitions exist. metric_dependency_
- **Why is occupancy low?** — M.OCC.001 is SHOW_BOTH: the decomposition is presented per definition and is never merged into a single explanation (analytics_execution_spec.md 2.6). Conflicting definitions exist. metric_dependency_
- **How is the business doing?** — Materiality is undefined for every change: no threshold exists in the exported evidence or in any specification (insight_generation_spec.md 2 condition 3). Two of the four documented insight triggers 

---

## Questions the registry cannot answer

These are **structurally absent**, not failures. `question_understanding_spec.md` §3.3:
the resolver must recognise them as absent rather than improvising from adjacent
metrics.

- **Which apartments are under-utilized?** — Not determinable from exported evidence.
- **Which property is performing better?** — Not determinable from exported evidence.
