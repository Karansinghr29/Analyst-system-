# Data Quality Center Specification

The trust and reliability area. Built by `ViewModelBuilder.data_quality_center()` from
`data_quality_registry.csv` (32 findings) — no severity is re-judged in the UI.

---

## 1. Structure

Findings grouped by their recorded severity, in fixed order:

```
CRITICAL   4     ← highest, always expanded on open
HIGH       8
MEDIUM     …
LOW        …
INFORMATIONAL …
UNVERIFIED …
```

Counts come from the register. The UI does not promote or demote a finding — that would be the
system substituting its judgement for the analysis that produced the register.

---

## 2. Each finding

| Field | Source |
|---|---|
| DQ id | `dq_id` |
| Issue | `issue` |
| Business area | `business_area` |
| Affected rows / amount | `affected_rows` / `affected_amount` |
| **Affected metrics** | derived: every metric carrying this `dq_id` |
| **Affected trust levels** | the gate verdicts of those metrics |
| Root cause | `root_cause` |
| Root-cause confidence | `PROVEN` / `SUSPECTED` — never a percentage |
| Status | `status` |
| Evidence | `evidence_files` |
| Recommended investigation | `ai_handling` |

The two derived fields are the ones an owner actually needs: *which of my numbers does this
affect, and how much should I trust them because of it.*

---

## 3. Links back

Every finding links to its DQ id · the affected metric ids · any conflict ids · the evidence
files · the validation checks. The chain is navigable in both directions: from a finding to the
metrics it degrades, and from a metric to the findings degrading it.

---

## 4. The four CRITICAL findings

These are the ones that most change how the business reads its own numbers:

| Finding | Effect |
|---|---|
| `DQ.001` | 42.7% of invoices disagree internally on `amount_paid + balance = total` |
| `DQ.002` | The four-way tenant-dues conflict — no single receivables figure |
| `DQ.016` | Owner rent omitted from one profit definition, overstating it ~36.6% |
| `DQ.019` | `tenant_transactions` frozen since the 2026-04 migration |

Each appears in the owner insight feed under **Critical**, not buried under Definition Conflict —
an owner scanning for urgent problems would not look there.

---

## 5. Presentation rules

| Rule | Reason |
|---|---|
| Severity is never re-ranked in the UI | The register is the authority |
| A LOW finding is never styled as urgent | `ai_agent_roles.md`: never manufacture urgency |
| Root-cause confidence stays `PROVEN`/`SUSPECTED` | No calibration exists for a numeric score |
| A finding with no recorded exposure says so | *Not determinable from exported evidence.* — not zero |
| Every finding shows its affected metrics | A DQ id with no visible consequence is ignorable |

---

## 6. Relationship to the insight feed

The DQ Center is the **complete** register, all severities. The owner insight feed carries only
CRITICAL and HIGH as standing proactive candidates — `insight_generation_spec.md` §2 condition 1.

Both read the same register. The feed is a filtered view of it, never a separate list.
