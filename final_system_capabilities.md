# Final System Capabilities

What the complete system can do, what it cannot, and — for each limitation — whether it is a gap
in this build or a property of the evidence.

That distinction is the whole point of this document. A limitation that comes from the evidence
cannot be engineered away, and a roadmap that promises to "fix" one is promising to invent data.

---

## 1. Capability summary

**56 capabilities across 9 analyst roles: 52 implemented, 4 limited-and-declared.**

| Domain | Capabilities | Status |
|---|---|---|
| Data analysis | KPI lookup, trend, period comparison, segmentation, dimensional analysis, drill-down, reconciliation | implemented |
| Business analysis | performance, operational efficiency, risk scan, recommendation, cross-domain synthesis | implemented |
| Financial | P&L, revenue, expenses, collections, AR, deposits, ledger, cash, owner payments, reconciliation, accounting consistency | implemented |
| Operations | occupancy, tenant lifecycle, maintenance, EB, utilization | implemented |
| Diagnostic | driver analysis, relationship analysis, pattern discovery | implemented |
| | trend break, anomaly surface | **PARTIAL** — no threshold exists |
| | statistical summary | **NOT IMPLEMENTED** — no method specified |
| | bed/apartment utilization | **PARTIAL** — NOT_DETERMINABLE in the registry |
| BI | KPI cards, trend views, comparisons, breakdowns, filters, drilldowns, narratives, definitions, DQ indicators | implemented |
| Reporting | executive summary, management briefing, what-changed | implemented |
| Decision support | recommendations, attention items, pending decisions, investigation priority | implemented |
| Risk / DQ | DQ scan, conflict surface, trust advisory, risk ranking | implemented |

---

## 2. What the system can do

- **Answer without being asked** — a 7-section briefing covering 20 KPIs, 20 ranked insights,
  period changes, owner decisions, and recommendations.
- **Answer any of the catalogued business questions** in owner language, with the analyst lens
  inferred rather than selected.
- **Explain any answer** back to source CSV rows and the validation check that confirmed the
  reconstruction.
- **Preserve every conflict** across every surface — dashboard, role views, BI cards, briefing,
  insight feed, decision queue, conversation.
- **Hold a multi-turn conversation** with additive-only inheritance, five-state clarification,
  explicit definition selection, and user correction.
- **Refuse safely**, with a stated reason, in every case where the evidence cannot support an
  answer.
- **Resist an uncooperative LLM** — the verbalization guard discards a model output that invents
  a number, drops a caveat, collapses a conflict, or leaks PII.

---

## 3. What the system cannot do — and why

### 3.1 Limitations from the *evidence* (cannot be engineered away)

| Cannot | Because |
|---|---|
| Say whether a change is material | No threshold exists in any specification or in the evidence. `insight_generation_spec.md` §2 condition 3 defers it to a business decision |
| Detect anomalies | `analytics_execution_spec.md` §2.5 leaves the statistical method open |
| Assert a cause | No experiment or control exists. Drivers are patterns over documented edges |
| Compare properties | One property exists |
| Quote a benchmark | The evidence contains only this business's own records |
| Report bed/apartment occupancy | `M.OCC.003`/`M.OCC.004` have no exported reference |
| Answer historical aging | The buckets were computed once at query time, not preserved |
| YoY for maintenance or EB | 20 months and 1–5 months of coverage |
| Resolve a definition conflict | Only an owner may decide which definition is authoritative |
| Identify a tenant by name | 27 PII columns are excluded from the export |

**Every one of these returns "Not determinable from exported evidence." with a specific reason.**
None returns an estimate.

### 3.2 Limitations of this *build* (could be extended)

| Not implemented | Note |
|---|---|
| `M.OCC.005` historical day-weighted occupancy | Interval logic out of Phase 1 scope; trust posture still SHOW_BOTH |
| 20 metrics unvalidated | No exported reference existed in Phase E; reported UNVERIFIED, never as MATCH |
| `M.RISK.007` 214 vs H.056's 187 | Documented reconstruction-method discrepancy; status DIFFERS |
| 11 of 49 metrics unreachable by phrase | Reachable by explicit `metric_id`; a real LLM would improve phrase coverage |
| Deterministic phrase matching, not NLU | The Phase 4 provider abstraction accepts a real model without changing anything below it |
| `follow_up` intent modelled, not implemented | Needs richer conversation state |

---

## 4. Verification state

| Layer | Evidence |
|---|---|
| Metric reconstruction | 70 PASS / 4 documented DIFFERS across 80 checks |
| Trust propagation | Clean audit, both directions (no missing and no false downgrades) |
| Analytics planning | 48/48 plans schema-valid, trust delegated verbatim |
| LLM boundary | 34/34, 11/11 exit criteria, hostile-model cases held |
| Insights & conversation | 31/31 scenarios, 0 trust violations |
| Analyst intelligence | 34 scenarios, 0 failures |
| **Automated tests** | **670 passing across Phases 1–6** |
| Source evidence | 253 CSVs byte-identical; SHA-256 verified each phase |

---

## 5. The honest summary

This system will not tell an owner something it cannot support. That is its main feature, and it
is also why it will sometimes feel less capable than a tool that would happily print a profit
figure. The three most important numbers in this business — profit, tenant dues, occupancy —
genuinely do not have single agreed values in the exported evidence. A system that produced one
anyway would be more satisfying and less true.

What it does instead is show all the definitions, name the disagreement, quantify it, and put the
decision in front of the person entitled to make it.
