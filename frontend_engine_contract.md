# Frontend ↔ Engine Contract

The complete interface between the presentation layer and the intelligence engine.

---

## 1. The prohibition list

The frontend **must never**:

| Prohibited | Structurally prevented by |
|---|---|
| Calculate a business metric | Payloads carry values, not formulas |
| Query CSVs or a database | No source handle is ever serialised |
| Override a trust level | `trust.trust_level` is read-only output |
| Select a conflict definition | `headline_permitted=false` + no `value` field populated |
| Invent a missing value | NOT_DETERMINABLE payloads carry an explicit reason, no placeholder |
| Infer causality | Driver output arrives pre-labelled OBSERVATION/HYPOTHESIS |
| Bypass validation | `validation_status` travels with every value |
| Ask an LLM for a number | Verbalization is guarded server-side and discardable |

The validator's check 10 enforces the first two by inspecting every payload for keys matching
`sql`, `query`, `formula`, `expression`, `connection`, `table`, `csv_path`, `raw_rows`,
`aggregation_fn`, `dsl`.

---

## 2. Payload shapes

### MetricTile
```
metric_id · title · section · widget · headline_permitted
value · display_value · unit            (only when headline_permitted)
definitions[{label, value, display_value}]   (only when NOT headline_permitted)
trust{trust_level, owner_status, owner_label, owner_explanation, badge, tone, icon,
      headline_permitted, prominence}
caveat · conflict_ids · dq_ids · evidence · validation_status · confidence · as_of
chart_type · drilldown_dimensions · ai_entry_points · unavailable_reason
```

**The invariant:** `value` and `definitions` are mutually exclusive. A tile never carries both,
so a frontend cannot choose between them.

### InsightCard
```
insight_id · category · category_label · what_happened · why_it_matters
evidence · confidence · recommended_action · risk · what_would_change_it
trust · conflict_ids · dq_ids · metric_ids · affected_amount · affected_count
ai_entry_points
```

### ChangeCard
```
metric_id · title · direction · display_change · current_period · previous_period
materiality_note        ← always states materiality is undefined
coverage_note           ← names any excluded incomplete period
unavailable_reason · trust · ai_entry_points
```

---

## 3. Entry points

Every clickable object carries `ai_entry_points`, each `{action, label, question, metric_id}`.
The frontend sends `question` to `AnalystIntelligence.ask()` verbatim.

An entry point is offered **only where the engine can answer it**. A snapshot-only measure gets
no "Why?" button, because "why did it change?" presupposes a change that cannot be established —
a button that always fails is worse than an absent one.

---

## 4. Error and state vocabulary

The frontend must distinguish six states that look similar and mean different things:

| State | Meaning | Payload signal |
|---|---|---|
| Loading | request in flight | client-side only |
| No data | the query ran, the result set is empty | `value` present, zero/empty |
| No evidence | the source is absent | `unavailable_reason` cites the missing file |
| Not determinable | the evidence cannot support it | exact phrase in `unavailable_reason` |
| Blocked | definitions conflict | `headline_permitted=false`, `definitions[]` |
| System error | the engine failed | error envelope, never a value |

Collapsing any two of these is a correctness failure. "No data" and "not determinable" rendered
identically would tell the owner a measured zero where the truth is an unmeasurable quantity.

---

## 5. Determinism

The same request returns the same payload. The frontend may cache **values**; it must never
cache **trust**, because a stale trust level is a correctness failure rather than a stale
number.
