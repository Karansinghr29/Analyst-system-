# Role-Based Analytics Specification

Nine analyst roles, **one system**. Not nine systems that happen to share a database — nine
*lenses* over the same semantic layer, analytics engine, trust gate, validation, reasoning, and
evidence chain.

`ai_agent_roles.md` §1 settled this and the implementation follows it:

> "These are **not** six separate functional roles to implement — they are six **domain lenses**
> the same underlying functional pipeline must be able to apply."

`role_view_registry.csv` (**334 role/metric views, generated from the live system**) records, for
every role × metric pair: the trust level, whether a headline is permitted, what that role may
conclude, and what it must never claim. A permission there can never be looser than the trust
policy allows, because it is *derived from* the gate's verdict.

---

## 1. The shared spine

Every role consumes, without exception or override:

```
semantic_metric_registry.csv → engine/gate.py → engine/execution.py → engine/validator.py
   → engine/business_reasoning.py → engine/explainability.py
```

Three invariants follow, and all three are tested:

1. **One definition per metric, across all roles.** The Financial Analyst's "revenue" and the BI
   Analyst's "revenue" are the same `M.REV.001` with the same filters. The consistency validator
   fails if any role view's metric name differs from the registry's.
2. **One trust verdict, across all roles.** No role sees a looser posture than another.
3. **No role can introduce a metric.** Roles claim `domain` values, not metric lists.

---

## 2. The nine roles

Six are defined by `ai_agent_roles.md` §1. Three are declared Phase 6 compositions of existing
machinery — marked in `analyst_role_registry.csv`'s `origin` column so the distinction between
"the spec said so" and "we assembled it" stays visible.

| Role | Origin | Domains | Reachable metrics |
|---|---|---|---|
| Data Analyst | spec | all 3 | 49 |
| Business Analyst | spec | Financial, Operations | 40 |
| Financial Analyst | spec | Financial | 24 |
| Operations Analyst | spec | Operations | 16 |
| Data Scientist / Diagnostic | spec | all 3 | 49 |
| BI Analyst | spec | all 3 | 49 |
| Management Reporting | composed | all 3 | 49 |
| Decision Support | composed | all 3 | 49 |
| Risk / Data Quality | composed | Risk & DQ | 9 |

---

## 3. Per-role definition

### 3.1 Data Analyst
- **Objective:** answer *what is the number, and how does it break down.*
- **Asks:** "What is revenue?" · "Show it by month" · "Break that down by category"
- **Capabilities:** `kpi_lookup`, `trend`, `period_comparison`, `segmentation`,
  `dimensional_analysis`, `data_quality_check`, `metric_reconciliation`, `drill_down`,
  `root_cause_exploration`
- **May conclude:** the value, at the documented grain, with its validation status.
- **Must never:** introduce a metric, dimension, or grouping the semantic layer does not
  document.

### 3.2 Business Analyst
- **Objective:** cross-domain synthesis and business framing.
- **Asks:** "How is the business doing?" · "Where are we losing money?" · "What needs attention?"
- **Capabilities:** `business_performance`, `operational_efficiency`, `business_risk_scan`,
  `recommendation`, `cross_domain_synthesis`
- **May conclude:** a synthesis across domains, each component keeping its own trust label.
- **Must never:** blend competing definitions into one business conclusion.

### 3.3 Financial Analyst
- **Objective:** P&L, revenue, expenses, collections, AR, deposits, ledger, cash, owner
  payments, reconciliation, accounting consistency.
- **Metrics:** the 24 Financial-domain metrics.
- **May conclude:** a financial figure where exactly one definition exists.
- **Must never — the sharpest boundary in this document:** state a single financial truth where
  the evidence carries competing definitions. Profit, tenant dues and owner rent are each
  presented as their competing definitions, always.

### 3.4 Operations Analyst
- **Objective:** occupancy, beds, apartments, tenants, lifecycle, maintenance, electricity.
- **May conclude:** operational counts and states at the documented grain.
- **Must never:** present a bed- or apartment-grain occupancy figure — `M.OCC.003`/`M.OCC.004`
  are NOT_DETERMINABLE, so the answer is exactly "Not determinable from exported evidence.", not an approximation.

### 3.5 Data Scientist / Diagnostic Analyst
- **Objective:** trends, changes, drivers, relationships.
- **May conclude:** a change occurred; a documented dependency moved alongside it.
- **Must never:** apply a statistical method or threshold no specification defines, or assert a
  cause. `analytics_execution_spec.md` §2.5 leaves the anomaly method open, so anomaly detection
  does not fire — it reports that it cannot, rather than inventing a cutoff.

### 3.6 BI Analyst
- **Objective:** KPI cards, trend views, comparisons, breakdowns, filters, drilldowns.
- **May conclude:** what the card contract permits, and no more.
- **Must never:** emit a KPI card without its trust level, conflicts and DQ indicators; or render
  a conflicted metric as a single tile.

### 3.7 Management Reporting Analyst
- **Objective:** the executive briefing.
- **Must never:** collapse a SHOW_BOTH/BLOCK metric into a single headline KPI for brevity.

### 3.8 Decision-Support Analyst
- **Objective:** recommendations and pending owner decisions.
- **Must never:** recommend an operational action on a BLOCK metric's disputed figure. The only
  recommendation available there is to resolve the conflict.

### 3.9 Risk / Data-Quality Analyst
- **Objective:** the DQ register, conflicts, trust posture.
- **Must never:** manufacture urgency for a LOW/INFORMATIONAL finding.

---

## 4. Routing — the owner never picks

Routing is deterministic, from the metric's `domain` plus the question's intent:

```
1. domain lens of the metric answered      (most direct — leads)
2. intent lenses                            (lookup / trend / driver / risk / recommendation)
3. risk-DQ lens whenever trust != SAFE      (the conflict is part of the answer)
4. BI + business lens on a structural limit ("only 1 property exists" is a business fact)
```

| Question | Lenses |
|---|---|
| "Why did profit fall?" | Financial + Data Scientist + Business + Risk/DQ |
| "What is occupancy?" | Operations + Data Analyst + Risk/DQ |
| "Which expense category is largest?" | Financial + Data Analyst |
| "Which property is performing better?" | Data Analyst + BI + Business → structural limitation |

---

## 5. Multi-lens synthesis

A metric appears under **exactly one** lens — the most direct that claimed it. Lenses cannot
contradict each other because they all read the *same executed answers*; there is no second
computation to disagree with.
