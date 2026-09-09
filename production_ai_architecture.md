# Production AI Architecture

The end-to-end production design, with the deterministic/LLM boundary drawn explicitly.

**Nothing in this document is built yet.** Phase 7 is a blueprint; deployment, live database
connectivity, a real LLM provider, authentication and the frontend are Phase 8+ and are gated on
the roadmap.

---

## 1. Full pipeline

```
┌── EVIDENCE ────────────────────────────────────────────────────────────┐
│ 253 exported CSVs, immutable · file_manifest.csv resolves every read   │
└────────────────────────┬───────────────────────────────────────────────┘
                         ▼
┌── DATA INGESTION ──────────────────────────────────────────────────────┐
│ manifest-driven loading · dtype coercion · lru-cached                  │
│ FUTURE: a live connector replaces this layer and NOTHING above it      │
└────────────────────────┬───────────────────────────────────────────────┘
                         ▼
┌── SEMANTIC LAYER ──────────────────────────────────────────────────────┐
│ 49 metrics · dimensions · conflicts · DQ register · dependency graph   │
└────────────────────────┬───────────────────────────────────────────────┘
                         ▼
┌── TRUST / CONFLICT GATE ───────────────────────────────────────────────┐
│ BINDING. Runs BEFORE execution. Worst-of: own level, dependency        │
│ propagation, documented floor. Nothing downstream may soften it.       │
└────────────────────────┬───────────────────────────────────────────────┘
                         ▼
┌── ANALYTICS EXECUTION ─► VALIDATION ───────────────────────────────────┐
│ documented filters/aggregations only │ 80 checks + sanity checks HALT  │
└────────────────────────┬───────────────────────────────────────────────┘
                         ▼
┌── QUESTION UNDERSTANDING ─► BUSINESS REASONING ─► INSIGHTS ────────────┐
│ intent/metric/dimension/time │ ladder, ceiling-gated │ ranked findings │
└────────────────────────┬───────────────────────────────────────────────┘
                         ▼
┌── ROLE ROUTING ─► BI CONTRACT ─► DECISION SUPPORT ─► ANSWER CONTRACT ──┐
└────────────────────────┬───────────────────────────────────────────────┘
                         ▼
╔═══════ LLM VERBALIZATION — UNTRUSTED, GUARDED, DISCARDABLE ═══════════╗
╚════════════════════════┬══════════════════════════════════════════════╝
                         ▼
                    OWNER UI  (not built)
```

---

## 2. The deterministic / LLM split

The LLM touches the pipeline in exactly **two** places, both fenced:

| # | Where | What it may do | How it is contained |
|---|---|---|---|
| 1 | Question understanding | Propose a **concept** and an **intent** | Validated against a closed contract. No field carries a value, table, column, SQL fragment, or trust level — so it *cannot* calculate, query, or assert trust. An invented metric is rejected before execution |
| 2 | Verbalization | Re-word a finished skeleton | Checked against the skeleton. A new number, dropped caveat, collapsed family, BLOCK headline, or PII reference causes the whole verbalization to be discarded in favour of the deterministic text |

There is no third place. **Everything authoritative is computed before the LLM is called**, and
the system is complete and correct with the LLM disabled entirely.

### Why the contract shape matters more than the prompt

A prompt is a request for cooperation. The contract is a structural constraint: the model has no
channel through which to send a number or a query, so it cannot send one regardless of what it
"decides" to do. Prompts make the cooperative path easy; the contract makes the uncooperative
path impossible.

---

## 3. Provider abstraction

One method — text in, text out. Everything that makes the system safe lives outside it, so
swapping providers cannot weaken any guarantee. The default is an offline deterministic provider;
a live model is **opt-in**, never a silent default, so no test or script can accidentally require
network access or spend credentials.

A provider failure degrades to a refusal, never to a guess.

---

## 4. Live-database migration (future)

The ingestion layer is the *only* layer a live connector replaces. But
`implementation_roadmap.md` attaches an unconditional requirement:

> "if/when the system moves from the static exported evidence to a live database connection,
> every trust rule, conflict, and DQ finding documented in this project must be **re-verified
> against live data before being trusted to still hold** — a conflict resolved in the live system
> must trigger an update to `semantic_metric_registry.csv`'s trust level, never a silent
> divergence."

So migration is not a connectivity task. It is a re-validation task with a connectivity step in
it. Two additional constraints: **no live DB modification** (read-only), and the snapshot-date
semantics that currently fix `2026-08-29` must be re-derived rather than carried forward.

---

## 5. Determinism and caching

The evidence is immutable, so identical questions return identical answers. Caching is permitted
for **evidence loads and computed values**; it is forbidden for **trust posture** — a stale trust
level would be a correctness failure, not a performance trade-off.

---

## 6. Failure modes and their handling

| Failure | Handling |
|---|---|
| LLM unavailable | Refuse and say so. Never guess at an unread question |
| LLM returns malformed output | One bounded repair attempt, then clarification. Never execute |
| LLM invents a metric | Rejected at the contract; no repair attempted (re-prompting cannot make it exist) |
| Verbalization violates a guard | Discarded whole; deterministic skeleton shown |
| Sanity check fails | **Halt.** A failed check indicates an engine bug, not a business fact |
| Evidence file missing | `EvidenceNotAvailable` → exactly "Not determinable from exported evidence." |
| Metric not implemented | NOT_DETERMINABLE naming the scope gap |

---

## 7. Explicitly out of scope for Phase 7

Web UI · Power BI implementation · live Supabase connector · production LLM deployment ·
authentication · RAG / vector database · autonomous agent loops.

Autonomous agents are excluded on principle, not merely on sequencing: an agent loop that could
re-plan around a BLOCK verdict would defeat the gate. Any future agent must call the same
`AnalystIntelligence.ask()` surface, under the same guards.
