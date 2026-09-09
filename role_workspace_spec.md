# Role Workspace Specification

Nine workspaces over **one** engine. Generated source: `role_workspace_registry.csv`.

Phase 8 brief 7: "These are NOT separate data systems. They must use the same 49 metrics,
semantic layer, trust gate, validation, reasoning, insight engine. Only the presentation,
workflows and analytical lens change."

Every workspace row carries `shares_semantic_layer=True` and `shares_trust_gate=True`, and the
validator fails any that does not.

---

## 1. The workspaces

| Workspace | Metrics | Conflicted tiles | Priority |
|---|---|---|---|
| **Owner** | 20 (curated) | 3 | What happened · Why · What matters · What to do |
| **Business Analyst** | 40 | 6 | Business problem · driver · impact · decision |
| **Data Analyst** | 49 | 12 | Metric · dimension · period · breakdown · validation · evidence |
| **Data Scientist** | 49 | 12 | Patterns · distributions · trend changes · statistical limits |
| **Financial Analyst** | 24 | 8 | Revenue · expenses · profit · collections · receivables · cash |
| **Operations Analyst** | 16 | 4 | Occupancy · tenancy · maintenance · EB |
| **BI Analyst** | 49 | 12 | KPI · report · dashboard · comparison · drilldown |
| **Risk / DQ Analyst** | 9 | 0 | DQ register · conflicts · trust posture |
| **Management Reporting** | 49 | 12 | The executive report |

A metric appears in a workspace when its registry `domain` matches the role. Roles claim
domains, never metric lists — so a role cannot acquire a metric by being edited.

---

## 2. What changes between workspaces, and what does not

| Changes | Does not change |
|---|---|
| Which metrics are foregrounded | The metric definitions |
| Default period and grouping | The trust verdict |
| Which panels open first | The validation status |
| Terminology density | The evidence chain |
| Depth of drilldown offered | Whether a headline is permitted |

The Financial Analyst revenue tile and the BI Analyst revenue tile are the **same** `M.REV.001`
with the same filters and the same value. The consistency validator fails if any workspace shows
a metric name differing from the registry.

---

## 3. Owner versus analyst framing

**Owner** sees business language and the trust translation: *"No single reliable figure —
definitions conflict."* Technical state travels in the payload but is not the headline.

**Analyst** workspaces surface the machine vocabulary alongside it: `BLOCK`, `C.010`, `DQ.016`,
`validation_status: MATCH`, the calculation trace. Nothing is hidden from the owner — it is one
click away — and nothing is added for the analyst that the owner could not reach.

---

## 4. Per-role boundaries

Each role declares what it must never claim, carried verbatim into every workspace row:

- **Data Analyst** — never introduce a metric, dimension or grouping the semantic layer does not
  document.
- **Financial Analyst** — never state a single financial truth where competing definitions exist.
- **Operations Analyst** — never present a bed- or apartment-grain occupancy figure
  (`M.OCC.003`/`M.OCC.004` are NOT_DETERMINABLE).
- **Data Scientist** — never apply a statistical method or threshold no specification defines.
- **BI Analyst** — never emit a KPI card without trust, conflicts and DQ indicators.
- **Business Analyst** — never blend competing definitions into one conclusion.
- **Management Reporting** — never collapse a conflicted metric into one headline for brevity.
- **Decision Support** — never recommend action on a disputed figure.
- **Risk / DQ** — never manufacture urgency for a LOW/INFORMATIONAL finding.

---

## 5. Switching workspaces

Switching changes the lens, not the answer. A figure carried from one workspace to another is the
same figure with the same trust posture. A conflicted metric is conflicted in all nine.
