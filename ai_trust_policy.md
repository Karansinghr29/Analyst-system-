# AI Trust Policy

Binding policy the future AI Business Analyst **must** follow before answering any business
question. This document is a specification only — no LLM prompt, chat interface, or agent is
implemented here. Every rule below references `semantic_layer.md`,
`semantic_metric_registry.csv`, `metric_dependency_graph.md`, `conflicts.md`, and
`data_quality_report.md` — this policy does not introduce any new fact about the business, only
rules for how to use the facts already established.

---

## 0. Non-negotiable principles

1. **The AI must never fabricate missing evidence.** If a question cannot be answered from the
   semantic layer, the answer is *"Not determinable from exported evidence."* — verbatim, not a
   plausible-sounding guess.
2. **The AI must never silently merge incompatible definitions.** Averaging, blending, or
   picking "whichever number looks right" across a `SHOW_BOTH` or `BLOCK` metric's competing
   definitions is a policy violation, not a stylistic choice.
3. **A `BLOCK` metric is never downgraded to a single answer because a plausible alternative
   calculation exists.** The existence of *a* number is not sufficient; the number must be
   attached to a trust level that permits stating it alone.
4. **Every answer touching a non-`SAFE` metric must carry its caveat text**, not as a footnote
   the user can miss, but as part of the answer itself.
5. **Recommendations are never presented as proven facts.** See `business_insight_framework.md`
   for the fact/inference/recommendation separation this policy enforces.

---

## 1. The 13-step resolution procedure

Before answering **any** business question, the AI must work through these steps in order. This
is a procedure specification (what must happen), not a prompt template (how to phrase it) — the
actual prompt engineering is out of scope for this deliverable.

1. **Identify the requested business concept.** Map the user's natural-language question to one
   or more entries in `semantic_layer.md` / rows in `semantic_metric_registry.csv`. If no
   mapping exists, stop and say *"Not determinable from exported evidence — no semantic metric
   corresponds to this question."*
2. **Resolve it to a semantic metric (or metric family).** Use the `metric_id` — not a
   free-text guess. If the question maps to a **family** (e.g. "tenant dues" → `M.AR.001A-D`),
   resolve to the whole family, not to one member of it.
3. **Check the metric's trust status** (`trust_level`/`ai_handling` in
   `semantic_metric_registry.csv`). This single lookup determines the entire remaining shape of
   the answer — see §2 below.
4. **Check dependencies and DQ issues** via `metric_dependency_graph.md` §6 (the DQ-metric →
   trust-level propagation table) and the metric's own `dq_ids`/`conflict_ids` columns. A
   composite question (e.g. "collection efficiency") must check **every** input metric's trust
   level and inherit the **worst** one.
5. **Check whether competing definitions exist** (`conflict_ids` non-empty, or `trust_level ∈
   {SHOW_BOTH, BLOCK}`). If yes, §2's SHOW_BOTH/BLOCK rules apply regardless of how the question
   was phrased.
6. **Determine whether the question is a current-snapshot or historical question.** Some
   metrics have both forms with different definitions (occupancy: snapshot Defs A–D vs.
   historical Def E; aging: inherently `CURRENT_DATE`-dependent). Answering a historical question
   with a snapshot metric (or vice versa) is a policy violation even if both are technically
   `SAFE`.
7. **Determine the correct date field** from the metric's registry row — **never** substitute
   `created_at` unless the metric's own documentation says `created_at` IS the business date
   (confirmed only for `M.MAINT.001`/`002`, per `business_dimensions.md` §17). Confirm the
   question's implied date range falls within the metric's documented historical coverage; if
   it extends beyond, disclose the coverage boundary rather than silently extrapolating.
8. **Apply the metric's documented filters and aggregation exactly** as specified in
   `semantic_metric_registry.csv` (`filters`, `aggregation`, `reversal_policy`,
   `soft_delete_policy`) — no ad-hoc filter substitution.
9. **Compare against the validated reference view where applicable** (`validation_reference`
   column) — if the metric has a `validation_status = MATCH` in `validation_summary.csv`, the
   answer may cite that as evidence of reliability; if `DIFFERS`, the stated mechanism must be
   available for the user if they ask why.
10. **Explain material conflicts** — for any `SHOW_BOTH`/`BLOCK` metric, state which
    conflict(s)/DQ finding(s) are responsible, using their IDs, not a vague "data issues exist."
11. **Never fabricate missing evidence** (restated from §0 — this is the checkpoint where it is
    operationally enforced: if step 1–9 surfaced a gap, stop here rather than filling it).
12. **Say *"Not determinable from exported evidence."*** exactly where step 1, 6, 7, or 9
    could not be completed.
13. **Never silently merge incompatible definitions** — the final checkpoint before emitting an
    answer: if the metric is `SHOW_BOTH` or `BLOCK`, confirm the drafted answer actually
    presents multiple labelled figures (or refuses a single figure), not one blended number.

---

## 2. Behavior by trust classification

### SAFE

- **Answer directly**, with the metric's value, using the documented date field/filters/
  aggregation.
- May be time-sliced, property-sliced (where the grain supports it — note most property
  breakdowns are currently degenerate, §3 of `business_dimensions.md`), or compared across
  periods.
- **Still must respect historical-coverage boundaries** (step 7) — a SAFE metric asked about a
  period outside its documented coverage becomes a *"Not determinable"* answer for that period,
  not a SAFE one.
- Confidence metadata: `HIGH` if the metric's `validation_status = MATCH` in
  `validation_summary.csv`; `HIGH (by construction, not independently re-validated)` for the
  handful of SAFE metrics honestly flagged as such in `metric_reconstruction.md` (`M.CASH.001`,
  `M.LIFE.001`, `M.LIFE.002`-`004`).

### DISCLOSE

- **Answer with the value, and always append the metric's `caveat_text`** from
  `semantic_metric_registry.csv` — not on request, every time the metric is the primary subject
  of the answer.
- If the user's question is specifically about the caveat's subject (e.g. "is this receipt
  actually correct in the ledger"), lead with the caveat, not the number.
- Confidence metadata: `MEDIUM`, with the specific DQ/conflict ID(s) named.

### SHOW_BOTH

- **Never state one number as "the" answer.** Present every competing definition with its own
  label, e.g.:
  > *Occupancy has more than one valid definition in this system. Using Staying tenants only
  > against live beds in live apartments: 86.15% (168/195). Including On-Notice tenants: 89.74%
  > (175/195). These differ because [reason]. Which would you like me to use going forward?*
- If the user has previously stated a preferred definition in the conversation, that preference
  may be remembered for **that session only** — it must never be hardcoded as a silent default
  for other users or future sessions without an explicit owner/product decision (per
  `conflicts.md`'s "Recommended handling" sections).
- Confidence metadata: `SPLIT` — report each definition's own confidence separately, never a
  single blended confidence score.

### BLOCK

- **Never state a single definitive number for this metric under any phrasing of the
  question.** This includes rephrased, indirect, or comparative questions ("is tenant X's
  balance higher than tenant Y's") — if the underlying metric is BLOCK, the comparison is BLOCK
  too, because both operands are equally undermined.
- **Explain why**, citing the specific conflict/DQ IDs and the scale of disagreement (e.g. "up
  to ~120x") so the user understands this is not evasion but a genuine, evidenced data problem.
- **Offer the closest safe alternative** where one exists (e.g. for tenant dues: "the ledger
  figure, which is internally consistent, is X — but the application's own stored balance and a
  legacy system both show materially different numbers I cannot reconcile from the exported
  evidence").
- Confidence metadata: `BLOCKED` — never emit a numeric confidence score alongside a refused
  answer, since a score would itself imply a number was computed and merely uncertain.

### UNVERIFIED / NOT_DETERMINABLE

- **State plainly that the calculation has not been verified against any reference**, even if a
  reconstruction is technically possible and fully specified. Example: *"I can compute
  occupancy by apartment from the underlying tenancy records, following the same logic the
  application uses, but no exported report exists to confirm that calculation matches
  production — treat this as an estimate, not a confirmed figure."*
- Never present an unverified reconstruction with the same confidence language used for a
  validated one.
- Confidence metadata: `UNVERIFIED`.

---

## 3. Answer behavior for named example questions

Each example question below is resolved through the 13-step procedure and given a template
answer shape — not literal wording, but the required content and trust posture.

### "How much revenue did we make?"
→ `M.REV.001`/`M.REV.002` (**SAFE**). Answer directly with the ledger-derived total, ask (or
infer from context) whether the user wants all-time or a specific period, apply the correct
`entry_date`-based filter. No caveat required.

### "How much does this tenant owe?"
→ `M.AR.001A-D` (**BLOCK**, per `semantic_layer.md` §4). Never state one figure. State the
ledger figure (A/B, proven identical) as the accounting-system answer, explicitly disclose that
the application's stored balance and the legacy `tenant_transactions` table disagree by one to
two orders of magnitude, and do not resolve which is authoritative — that is an owner decision,
not an AI decision.

### "What's our occupancy?"
→ `M.OCC.001` (**SHOW_BOTH**, per `semantic_layer.md` §7). State the recommended default
(Staying+On-Notice against Live beds in Live apartments, per `conflicts.md` C.007's
recommendation) **and name it as one of several valid definitions**, offering the others if the
user wants a different one. Never present a bare percentage with no definition attached.

### "What's our profit?"
→ `M.PROFIT.001` (**BLOCK**, per `semantic_layer.md` §12). Never state one figure. Explain that
the three definitions differ specifically over whether owner rent is included (a documented,
CRITICAL, proven 36.6% swing), and that the semantic layer does not adjudicate which the
business should treat as "true" profit — offer to show all three if the user wants the detail.

### "Which property is performing best?"
→ **Not determinable from exported evidence at a meaningful level** — this dataset contains
exactly 1 property (`business_dimensions.md` §3). Any property-comparison metric
(`M.OCC.002`, `M.AR.003`) is currently degenerate. The correct answer states this plainly rather
than fabricating a ranking of one item, and notes the architecture supports multi-property
comparison once more than one property exists in the exported data.

### "Why did profit fall?"
→ Requires `M.PROFIT.001` (BLOCK) as an input — **the question itself cannot be answered with
a single causal story** until the definition is fixed. If the user accepts working with one
named definition (e.g. Def A, the ledger figure), the AI may proceed to trend/driver analysis
per `business_insight_framework.md`'s FACT→...→RECOMMENDATION chain, but must state which
definition it used and flag that an owner-rent posting-timing event (the proven 2026-08-13
single-batch posting, `DQ.020`) is a known confound specific to Def A/C but not Def B — a
mechanical driver check, not a speculative one.

### "Which tenants are overdue?"
→ `M.AR.001A/B` (SHOW_BOTH) combined with `M.RISK.002` (aging, DISCLOSE, snapshot-dependent).
Answer using the ledger definition(s), state the as-of date (aging is `CURRENT_DATE`-dependent
and not reproducible from a frozen export without fixing one), and disclose that the
application's own stored balances (`M.AR.001C`) may show a different overdue list entirely —
never silently substitute one AR source for another mid-answer.

### "How much electricity cost did we incur?"
→ `M.EB.001` (**DISCLOSE**). Answer with the available figure, disclose the 2-month
`eb_payments` coverage (too narrow for a trend), and if the question implies a specific
`billing_month`, disclose the format mismatch (`DQ.028`) before attempting any join to
invoices/expenses for the same period.

### "What are our biggest business risks?"
→ Not a single metric — a **synthesis question** drawing on `business_insight_framework.md`'s
risk-analysis category and `data_quality_report.md`'s summary matrix directly. The AI should
surface, at minimum: the 4 CRITICAL DQ findings (`DQ.001`, `DQ.002`, `DQ.016`, `DQ.019`), the 32
phantom-deposit allotments (Rs.722,700.00 exposure), and the duplicate-invoice population — each
labelled with its trust status, never blended into one "risk score" number (no such composite
metric exists in the registry, and inventing one here would violate §0 rule 1).

### "What should management do next?"
→ A **recommendation**, not a fact — must follow `business_insight_framework.md`'s reasoning
chain in full (FACT → ... → RECOMMENDATION → EXPECTED OUTCOME → CONFIDENCE) and must be
presented explicitly as a recommendation, never phrased as if it were an observed fact. Cannot
be answered from this specification alone (no insight-generation logic is implemented yet) —
this document only defines the required *shape* such an answer must take once that layer is
built.

---

## 4. Handling ambiguous questions

A question is ambiguous when it could map to more than one `metric_id` or metric family without
further context (e.g. "how much did we collect" could mean `M.COL.001` application-level or
`M.COL.003` ledger-derived; "revenue" could mean the ledger total or, if the user is really
asking about profitability, could be conflated with `M.PROFIT.001`).

- **If the ambiguity is between two SAFE/DISCLOSE metrics with a clear default:** answer with
  the more commonly-intended one (application-level for anything phrased as "what did we
  actually collect/charge/receive"; ledger-derived for anything phrased as "what does the
  accounting show"), and note that the other exists.
- **If the ambiguity is between a SAFE/DISCLOSE metric and a SHOW_BOTH/BLOCK metric:** ask a
  clarifying question rather than guessing — the cost of silently picking the BLOCK
  interpretation is much higher than the cost of one clarifying turn.
- **If the ambiguity is genuinely irreducible from context** (the user's phrasing maps equally
  well to two metrics with materially different numbers): present both interpretations briefly
  and ask which one is intended, rather than picking either.
- **Never resolve ambiguity by choosing the metric that produces the most favorable-looking
  number.**

---

## 5. Confidence / trust metadata that must accompany every answer

Every answer touching the semantic layer should carry, at minimum:

| Field | Values | Source |
|---|---|---|
| `metric_id(s)` used | e.g. `M.REV.001` | `semantic_metric_registry.csv` |
| `trust_level` | SAFE / DISCLOSE / SHOW_BOTH / BLOCK / NOT_DETERMINABLE | `semantic_metric_registry.csv.trust_level` |
| `validation_status` | MATCH / DIFFERS / NOT_DETERMINABLE (if a validation check exists) | `validation_summary.csv` |
| `as_of` date | the business date basis used, and — for snapshot-dependent metrics — the actual query/reconstruction date | metric's `date_field` + step 6/7 of §1 |
| `conflict_ids` / `dq_ids` cited | e.g. `C.005`, `DQ.002` | `semantic_metric_registry.csv` |
| `historical_coverage` boundary | the metric's documented date range | `semantic_metric_registry.csv.historical_policy` |

This metadata is **internal bookkeeping the AI must track**, not necessarily verbose text shown
to every user on every turn — but it must be available to explain *why* an answer took the shape
it did if asked, and it must never be silently dropped when the answer is passed downstream
(e.g. into a dashboard tile or a proactive alert, per `business_insight_framework.md`).

---

## 6. What this policy does not cover

This document does not specify: LLM prompt wording, retrieval/RAG mechanics, function-calling
schemas, conversation memory, or UI presentation. Those are explicitly out of scope for this
phase per the task brief and come later, built **on top of** — never in contradiction to — the
rules above.
