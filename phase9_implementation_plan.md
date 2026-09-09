# Phase 9 Implementation Plan and Dependency Map

The production integration layer: connecting the Phase 1–8 deterministic engine to a real
application, without weakening a single guarantee it currently makes.

---

## 1. Scope boundary — what can honestly be built here

Phase 9 spans six workstreams. Three are fully buildable and testable offline. Three have a
**boundary** that is buildable and an **activation** that is not, because activation requires
credentials or infrastructure this environment does not have.

Stating that split up front, because building a "live connector" that cannot connect, and
reporting it as done, would be the kind of quiet overstatement this whole project is built to
avoid.

| Workstream | Boundary (built) | Activation (not built) | Why not |
|---|---|---|---|
| **W1 API service** | Full HTTP service over the view models | Deployment, TLS, scaling | Infrastructure |
| **W2 Conversation persistence** | Durable store, full lifecycle | Managed DB | Infrastructure |
| **W3 AuthZ** | Role→workspace authorization, session identity | Credential storage, IdP, password handling | Requires an identity provider; storing credentials is out of scope and hazardous to fake |
| **W4 LLM provider** | Adapter interface + config + guard wiring | A live model call | No authorized credential. `GROQ_API_KEY` exists in this environment but sending business data to an external service is not something I will do without explicit instruction |
| **W5 Live data connector** | Connector interface + **re-validation harness** | An actual Supabase connection | No credentials, and — more importantly — the roadmap forbids trusting live data until the harness passes |
| **W6 Frontend / Power BI** | OpenAPI schema + Power BI dataset descriptor | A built UI | Phase 10 |

**The honest headline:** Phase 9 delivers the complete *integration surface*. A team with
credentials plugs into it without touching the engine, the semantic layer, or any trust rule.

---

## 2. The rule that governs W5

My own Phase 7 roadmap, quoting `implementation_roadmap.md`, attaches an unconditional
requirement to live data:

> "every trust rule, conflict, and DQ finding documented in this project must be **re-verified
> against live data before being trusted to still hold** — a conflict resolved in the live system
> must trigger an update to `semantic_metric_registry.csv`'s trust level, never a silent
> divergence."

So W5 is **not** a connectivity task with validation bolted on. It is a re-validation harness
with a connector attached. The connector is deliberately built so that it **cannot serve the
engine until the harness passes** — a live source is quarantined by default, not trusted by
default.

That inversion is the single most important design decision in Phase 9. Treating live data as
plumbing is how a project like this loses everything it built.

---

## 3. Dependency map

```
                    ┌───────────────────────────────────┐
                    │  ENGINE (Phases 1–8) — UNCHANGED  │
                    │  49 metrics · trust gate ·        │
                    │  validation · view models         │
                    └────────────────┬──────────────────┘
                                     │ read-only
        ┌──────────────┬─────────────┼─────────────┬──────────────┐
        ▼              ▼             ▼             ▼              ▼
   ┌─────────┐   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ W3      │   │ W2       │  │ W4       │  │ W5       │  │ W6       │
   │ AuthZ   │   │ Conv.    │  │ LLM      │  │ Live     │  │ Export   │
   │         │   │ store    │  │ adapters │  │ connector│  │ contracts│
   └────┬────┘   └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
        │             │             │             │             │
        └─────────────┴──────┬──────┴─────────────┘             │
                             ▼                                  │
                    ┌──────────────────┐                        │
                    │ W1  API SERVICE  │◄───────────────────────┘
                    │  the only door   │
                    └──────────────────┘
                             ▲
                    frontend · Power BI · scripts
```

**Build order, and why:**

1. **W1 first** — everything else attaches to it, and building it first forces the service
   boundary to be defined before any client shapes it.
2. **W2, W3** next — both are prerequisites for a real session and are independent of each other.
3. **W4** — the provider boundary already exists (Phase 4 `CallableProvider`); Phase 9 adds
   config-driven adapter selection and failure handling.
4. **W5** — depends on nothing above it, but is last of the engine-adjacent work because its
   harness must run against a *stable* API.
5. **W6** — generated from W1's finished schema, so it cannot drift from what the service serves.
6. **W7 validator** — runs over all six.

---

## 4. Non-negotiable invariants

Every workstream is constrained by these. The Phase 9 validator checks each.

| Invariant | How W1–W6 preserve it |
|---|---|
| No business logic outside the engine | The API serves view models; it computes nothing |
| BLOCK exposes no headline | Serialised payloads carry no `value` field for BLOCK |
| SHOW_BOTH keeps every definition | Response schema requires `definitions[]` |
| NOT_DETERMINABLE keeps the exact phrase | Schema-level assertion on the response |
| Evidence chain survives | Every response carries `evidence` and `validation` |
| Trust is never cached | Cache policy forbids caching trust posture |
| Trust is not per-user | AuthZ filters *which* metrics a role sees, never *how* they are gated |
| LLM stays untrusted | Adapters sit behind the existing verbalization guard |
| Source CSVs immutable | SHA-256 check in the validator |
| No live DB modification | Connector interface is read-only by construction |

**The authorization subtlety worth naming:** a role may see fewer metrics, but never a *looser*
trust posture on a metric it can see. Trust is a property of the evidence, not of the viewer. An
authorization layer that could relax a conflict for a senior role would defeat the entire gate.

---

## 5. Workstream detail

### W1 — API service boundary
`api/` — FastAPI app. Endpoints mirror the Phase 8 view models exactly:

```
GET  /health
GET  /api/owner/home                    OwnerHome
GET  /api/metrics                       ui metric registry
GET  /api/metrics/{metric_id}           metric detail
GET  /api/metrics/{metric_id}/conflict  conflict view
GET  /api/insights                      ranked feed
GET  /api/changes                       period changes
GET  /api/data-quality                  DQ center
GET  /api/roles                         role registry
GET  /api/roles/{role_id}/workspace     role workspace
POST /api/ask                           natural-language question
GET  /api/conversations/{id}            conversation history
GET  /api/report/executive              management report
GET  /api/trust                         trust posture summary
```

No endpoint accepts a filter expression, a formula, or a metric definition. The request surface
carries only identifiers and already-catalogued dimension names.

### W2 — Conversation persistence
SQLite. Stores turns, resolved requests, plans, clarification state, and definition selections —
so a conversation survives a restart with its safety state intact. **An open clarification must
survive persistence**; a reloaded conversation that forgot it was awaiting an answer would treat
the next message as a fresh question.

### W3 — Authorization
Role→workspace mapping from `role_workspace_registry.csv`. Sessions carry a role. Authorization
answers "which metrics may this role see", never "how trusted are they for this role".

### W4 — LLM provider adapters
Config-driven selection over the existing `LLMProvider` interface. Ships `DeterministicMock`
(default, offline) and adapter *shapes* for HTTP-based providers. No vendor SDK, no network call,
no credential read at import time.

### W5 — Live connector + re-validation harness
A `DataSource` interface with two implementations: the existing manifest-backed export, and a
live connector stub. The harness re-runs the 80 validation checks, 24 conflicts, and 32 DQ
findings against any candidate source and returns a verdict. **A source that has not passed is
refused by the engine binding.**

### W6 — Export contracts
OpenAPI schema (generated from W1) and a Power BI dataset descriptor (generated from the metric
and visualization registries).

---

## 6. Anti-drift strategy

`scripts/validate_phase9_consistency.py` checks:

1. Every endpoint returns a schema-valid payload
2. Every served trust level matches the live gate
3. No BLOCK payload carries a headline
4. Every SHOW_BOTH payload carries all definitions
5. Every NOT_DETERMINABLE payload carries the exact phrase
6. No response carries a formula, query, or raw source handle
7. Every role workspace matches the role registry
8. AuthZ never alters a trust level
9. Conversation persistence round-trips clarification state
10. The live connector is quarantined until the harness passes
11. LLM adapters cannot bypass the verbalization guard
12. Source CSVs byte-identical

Plus the full Phase 1–8 regression (751 tests) unchanged.

---

## 7. Exit criteria

- All 751 existing tests pass, unmodified.
- Phase 9 tests pass.
- Phase 9 validator reports zero problems.
- Phases 2–8 validators/evaluations still pass.
- Source CSVs byte-identical to the recorded baseline.
- Every deferred item is named with the reason it is deferred — no silent gaps.
