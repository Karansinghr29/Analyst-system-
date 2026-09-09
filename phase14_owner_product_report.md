# Phase 14 — Owner Intelligence Product Completion

Completes the owner-facing product on top of the existing Phase 1–13 architecture. Nothing was
replaced: the analytics engine, Trust Gate, question planner, LLM boundary, insight engine,
Phase 9 API, Phase 11 security, Phase 12 Ollama adapter and Phase 13 live-data quarantine are
all reused as they stand. Five gaps were closed, four of which were product defects rather than
missing features.

---

## 1. What was actually wrong

Four of the five changes below fix behaviour that did not work, not behaviour that was missing.
Three of them were found by running the product, not by reading it.

### 1.1 The application could not authenticate itself

`api.js` exported `setToken()` and **nothing in the client ever called it**. The Phase 11 API is
fail-closed and requires a bearer token on every call, so a correctly-secured deployment rendered
as *"The analytics service refused the request — Authentication required."* with no way forward.
The product was unusable as shipped.

Fixed by `frontend/views/signin.js`: a gate that accepts the token the deployment issues, holds
it in `sessionStorage` for the tab, and re-routes. It is deliberately **not** a login form — it
creates no account, accepts no password, and performs no verification of its own. Verification
stays server-side where the secret is. `api.js` announces a 401 once via an event, so every
current and future call site is covered by one mechanism rather than ten error paths.

### 1.2 Conversation follow-ups could not work over HTTP

`ConversationContext.resolve()` fully supported "Why?" and "What about June?" — but
`ConversationStore.restore_into()` restored only the open clarification and definition
selections, **not the turn history**, and `AnalyticsService.ask()` clears the context before
restoring. So `context.last` was always `None` across an HTTP request and nothing was ever
inherited. Follow-ups worked in-process and silently failed in the product.

Two changes, both narrow:

* The store now persists the **structured interpretation** of each turn (concept, metric ids,
  period, intent) in a new `turns.request_json` column, with an additive migration for existing
  databases. The *answer* is still deliberately not restored — re-serving a past answer could
  serve a stale trust posture, which is why the original design excluded it. A request carries
  no figure and no posture, so restoring it cannot.
* A bare `"Why?"` is genuinely uninterpretable standalone, so the model correctly rejects it and
  the pipeline returned `NEEDS_CLARIFICATION` before context was ever applied.
  `ConversationContext.followup_seed()` now supplies an **empty** request in that one case, and
  `resolve()` fills it from the previous turn through the same additive inheritance every other
  follow-up uses. There is one inheritance path, not two.

**This is not a weakened guard.** The seeded request is planned by Phase 3 and gated by Phase 2
from scratch. Verified: `"What is our profit?"` → BLOCKED, then `"Why?"` → still BLOCKED, same
metric, no headline. A follow-up inherits the *subject*, never a permission.

### 1.3 Page loads took 11–28 seconds

Measured against the running server:

| Endpoint | Before | After (warm) |
|---|---|---|
| `/api/owner/home` | 11.2 s | ~1.1 s |
| `/api/analytics/financial` | 22.2 s | ~1.1 s |
| `/api/analytics/risk` | 15.5 s | ~1.0 s |
| `/api/metrics` | 27.9 s | ~1.1 s |

Every request re-ran the insight engine, change detection and the executive summary. Memoising
them is sound rather than merely convenient: the bound evidence is an **immutable export whose
SHA-256 is pinned**, so these payloads are a pure function of the source.

The cache key is the bound source's own descriptor, so the eventual read-only Supabase activation
discards every payload computed from the export instead of serving it on.

**Only the unfiltered payload is cached.** Authorization is applied to a copy on every request,
because caching a role-filtered payload would risk serving one role's view to another — a
security failure rather than a stale number. Tested directly
(`test_authorization_is_applied_after_the_cache`).

### 1.4 The owner's own words were not recognised

Found by running the ten owner scenarios end to end rather than by reading the code:

* **`"How is my business doing?"` did not reach the briefing.** `_BRIEFING_PHRASES` matched
  `"how is the business"` but not `"how is my business"` — which is the most natural owner
  phrasing *and the dashboard's own page title*. The question fell through to a metric lookup,
  resolved to no single metric, and was refused.
* **`"What are the biggest risks?"` had no route at all.** No risk phrasing appeared in any
  workflow list, so it depended entirely on the language model and returned
  `NEEDS_CLARIFICATION`. It is offered as a one-click question on the dashboard.

Both now route to deterministic workflows. Risk questions reach the attention queue — the BLOCK
conflicts and critical data-quality findings the insight layer already validated. They are
**not** answered by a risk score: no specification defines one, and inventing a ranking would be
exactly the fabrication this system exists to prevent.

`test_ui_questions_route_deterministically` now pins the routing of every phrase the UI offers as
a button, so a chip cannot silently start dead-ending. One chat suggestion
(*"Show me financial issues."*) had no honest deterministic destination and was replaced with
*"Which numbers should I trust?"*; domain-scoped exploration is what the Analytics sections are
for.

### 1.5 The analyst experience did not exist

Role workspaces existed (9 analyst lenses), but there was no owner-facing way to explore
analytics by business area.

---

## 2. What was built

### 2.1 AI Analyst workspace — four sections

`/api/analytics` and `/api/analytics/{section}`, rendered by `frontend/views/analytics.js`.

| Section | Source | Content |
|---|---|---|
| Financial | `domain = Financial` | 24 measures, 13 findings, 3 changes |
| Operations | `domain = Operations` | 16 measures, 4 findings |
| Risk & Data Quality | `domain = Risk & Data Quality` | 9 measures, 9 findings, 32 DQ findings |
| Business Insights | cross-domain | 22 findings, 11 decisions, 20 next steps |

The domains are read from `semantic_metric_registry.csv`; they were not invented for this phase.
Each section is a **slice of the same `owner_home()` payload the dashboard renders**, so a figure
on a section cannot disagree with the same figure on the dashboard. There is no second analytics
path.

### 2.2 Honest capability disclosure

`engine/capability_disclosure.py` joins `analysis_capability_registry.csv` with the analyst roles
(which already carry `domains`) so each section can state its own limits. Every section renders
two columns with equal prominence: *Available analysis* and ***Not available, and why*.**

The specifications deliberately decline to fix a materiality threshold, an anomaly bound, and a
statistical method. Those analyses are therefore **named as unsupported with the registry's own
reason**, rather than omitted or fabricated. Live example from the Risk section:

> **Anomaly surface** · PARTIAL — *"analytics_execution_spec.md 2.5 leaves the statistical method
> to the implementation phase; no anomaly threshold exists in the exported evidence. Not
> determinable from exported evidence."*

No threshold, benchmark or statistical method was invented anywhere in this phase.

### 2.3 Owner Home restructured

Three blocks, in the order an owner reads a business. Previously the attention queue sat *below*
the entire insight feed, so the items most needing a decision were furthest down the page.

1. **Executive snapshot** — business health, operations, risk indicators, and a trust summary.
2. **What needs my attention** — decisions awaiting the owner, then critical / attention /
   definition-conflict / data-quality findings, then validated period changes.
3. **Key insights** — positive and opportunity findings, then suggested next steps.

Presentation only. Same payload, same figures, same postures.

### 2.4 AI Business Analyst chat

Uses the existing `/api/ask` and the existing Ollama pipeline. No second chatbot architecture.

* An identity panel stating what this analyst is and is not — it looks like a general-purpose
  chatbot and is not one.
* Follow-up chips after every answer (`Why?`, `Explain this.`, `What changed?`,
  `What should I do?`, `Which area should I look at first?`). Each is a question the pipeline
  actually answers; the last three are deterministic workflows that run even when the language
  layer is unreachable.
* An explicit notice when the wording layer did not contribute, so a deterministic fallback is
  never presented as the model's own considered phrasing.
* Internal measure identifiers moved out of the answer header into the evidence chain, where
  they belong with the rest of the provenance.

### 2.5 `serve.py`

A launch entry point. Requires `AI_ANALYTICS_AUTH_SECRET` — there is no default, because a
default secret is a shared secret. Warms the payload cache before accepting traffic. Enables no
LLM adapter and connects to no live database; both remain opt-in through their own activation
paths.

---

## 3. Verification

### Test suite

**1006 passed, 2 skipped, 0 failed** (48 min 49 s). The two skips are the opt-in live tests,
correctly gated: `test_live_ollama_roundtrip_if_explicitly_flagged` and the live Supabase test.
63 of the passing tests are new in this phase.

### Default security posture, with no environment configured

```
llm      : QUARANTINED   network_access = False
source   : export        TRUSTED   (re-validation passed)
live     : live          UNAVAILABLE
auth     : QUARANTINED   enforced = True
```

No credential, secret, token or connection string was introduced. Supabase remains quarantined
and the CSV export remains the trusted serving source.

### Validators — all pass, 0 problems, 0 warnings

| Validator | Result |
|---|---|
| Phase 7 consistency | 0 problems, 0 warnings |
| Phase 8 presentation | 0 problems, 0 warnings — 111 entry points, 91 drill paths |
| Phase 9 integration | 0 problems, 0 warnings — export TRUSTED, 80/80 checks, 12/12 conflicts, 32/32 DQ findings reproduced |
| Phase 10 anti-drift | 0 problems, 0 warnings — 9 modules, 44 entry points, 17 API routes |
| Phase 11 activation | 0 problems, 0 warnings — live UNAVAILABLE, LLM QUARANTINED, auth TRUSTED |
| Phase 12 Ollama | 0 problems, 0 warnings — mock default `True` |
| Phase 13 live freeze | 0 problems, 0 warnings — export TRUSTED, live UNAVAILABLE |

Source integrity: SHA-256 `aed87d5270eca597…` **matches baseline** in every validator. No source
CSV was read for writing, and none changed.

### Trust guarantees, re-verified on the new surfaces

* No analytics tile carries a value when `headline_permitted` is false — asserted in tests and
  confirmed in the live DOM (20 tiles rendered, 0 headline leaks).
* SHOW_BOTH tiles present every competing definition; none collapses to one figure.
* A BLOCK follow-up stays BLOCKED and states no figure.
* The exact phrase *"Not determinable from exported evidence."* reaches the DOM unaltered.
* Analytics tile postures equal the gate's verdict for every metric in every section.
* Where the dashboard and an analytics section show the same measure, posture, permission and
  rendered value are identical.

---

## 4. Genuine remaining limitations

1. **`"Show me financial issues."`-style domain-scoped questions still depend on the model.**
   The deterministic workflows are business-wide, not per-domain. A domain-scoped question is
   answered precisely by the corresponding Analytics section instead.

2. **Local model latency.** `llama3.2` on this CPU takes ~17 s for a short prompt and exceeds
   60 s on the full concept-catalogue prompt, so the default 60 s timeout is too low for this
   hardware. The system degrades correctly — it refuses rather than guessing — but the honest
   configuration is to raise `AI_ANALYTICS_LLM_TIMEOUT` (supported, capped at 300) or run a
   smaller/faster model. Ollama's 5-minute default keep-alive also unloads the model between
   questions, making the next one pay a cold start.

3. **Materiality, anomaly bounds and statistical method remain undefined.** These are business
   decisions the specifications explicitly defer. The product names them as unsupported rather
   than inventing them. This is a limitation of the evidence, not of the implementation, and
   closing it requires an owner decision — not more code.

4. **Cold start.** The first build of all owner payloads takes tens of seconds on this hardware.
   `serve.py` pays it once at startup so the owner never does. There is no cross-process cache,
   so each server process pays it on boot.

5. **Supabase remains quarantined**, by instruction. The owner-facing UI reads only from the
   Phase 9 API and the memo re-keys on the source descriptor, so activating the read-only path
   requires no UI change.

6. **`/api/ask` remains the only surface where an owner can be blocked by model availability.**
   Every dashboard and analytics surface is fully deterministic and works with no model at all.
