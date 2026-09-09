# Phase 10 Implementation Plan — Production Owner Application

The actual application, built on the Phase 9 API and the Phase 8 view-model contracts.

---

## 1. Architecture decision: zero-build vanilla ES modules

**Chosen:** plain ES modules + HTML/CSS, served as static files by the existing FastAPI app.
**Rejected:** React/Vue with a bundler.

The reason is not preference. This system's central claim is *no calculation or business logic
outside the engine*, and the Phase 10 validator has to prove that about the code that actually
ships. With a bundler, the audited source and the shipped bundle are different artifacts —
minified, transpiled, tree-shaken — and the validator would be inspecting something other than
what runs. With ES modules, **shipped source is audited source**, and a scan for arithmetic on
business values is a scan of the real thing.

Secondary benefits: no toolchain to break, no dependency surface, and the app runs directly from
`uvicorn` with no build step.

The trade-off is real and worth naming: no component framework, so the render layer is hand-
written. That is acceptable because the UI is almost entirely *display of pre-formatted payloads*
— the hard thinking already happened in the engine.

---

## 2. The one rule the frontend must obey

> The frontend renders. It never computes.

Concretely, `app/js/**` must contain **no**:

- arithmetic on a business value (`+ - * /` over payload numbers)
- number formatting (the payload carries `display_value`)
- trust derivation (the payload carries `trust`)
- conflict resolution (`definitions[]` is rendered whole, in payload order)
- SQL, query strings, or direct evidence access
- LLM calls

The validator enforces each by scanning the shipped JS. A frontend that can compute is a
frontend that can disagree with the engine — and the disagreement would be invisible, because
both sides would look correct.

---

## 3. Dependency map

```
              ┌─────────────────────────────────────────┐
              │  ENGINE (Phases 1–8) — UNCHANGED        │
              └──────────────────┬──────────────────────┘
                                 │
              ┌──────────────────▼──────────────────────┐
              │  PHASE 9 API — the ONLY data boundary   │
              │  15 endpoints · no formula · no query   │
              └──────────────────┬──────────────────────┘
                                 │  fetch() only
        ┌────────────────────────▼─────────────────────────┐
        │  app/js/api.js      the single fetch wrapper      │
        │  ── every other module goes through this ──       │
        ├──────────────────────────────────────────────────┤
        │  trust.js    render.js    format.js(NONE)         │
        │  ── trust badges ── DOM ── (no formatting layer)  │
        ├──────────────────────────────────────────────────┤
        │  views/  dashboard · metric · conflict · chat ·   │
        │          roles · report · dq                      │
        ├──────────────────────────────────────────────────┤
        │  app.js     router + shell                        │
        └──────────────────────────────────────────────────┘
```

`api.js` is the only module that may call `fetch`. Everything else receives data as arguments.
The validator checks that no view module contains `fetch(` — which makes an accidental
second data path structurally visible rather than merely discouraged.

---

## 4. Incremental stages and their gates

Each stage must pass its gate before the next begins.

| Stage | Builds | Gate |
|---|---|---|
| **S1** | App shell, router, `api.js`, `trust.js`, Owner Dashboard | Dashboard renders 20 tiles; the 3 headline-forbidden tiles render no figure |
| **S2** | Metric detail, insight cards, conflict view, DQ centre, drilldown | Conflict view shows all definitions, selects no winner |
| **S3** | AI chat, conversation continuity, evidence chain panel | Answers carry evidence; clarifications persist across turns |
| **S4** | Role workspaces, executive report, decision queue | Same metric shows identical trust in every workspace |
| **S5** | Production data / LLM integration | **Only after** Phase 9 quarantine gates pass — see §6 |

---

## 5. Test and validation strategy

| Kind | What it proves |
|---|---|
| **Frontend contract tests** | Every view renders every payload shape the API can return, including empty and unavailable states |
| **Trust-regression tests** | BLOCK renders no headline; SHOW_BOTH renders all definitions; NOT_DETERMINABLE renders the exact phrase — asserted on rendered DOM, not on intent |
| **Accessibility checks** | Trust conveyed by text + icon, never colour alone; `aria-label` on every tile carries the trust label; conflict panels keyboard-navigable |
| **Responsive checks** | Conflicts stay expanded at every breakpoint — space pressure is exactly when the temptation to show one number appears |
| **Anti-drift validator** | 12 checks over the shipped JS and the served payloads |

Rendering is tested in Python by executing the render functions' contract against real API
payloads, plus static analysis of the shipped JS. No headless browser is required, which keeps
the suite runnable in this environment.

---

## 6. What stays quarantined, and what would lift it

**Live Supabase.** Not connected. Requires: a read-only connection string, and then
`RevalidationHarness` passing — all 80 checks, 12 conflicts, 32 DQ findings re-verified. Until
`bind_source()` accepts it, the app serves the export.

**Production LLM.** Not connected. `GROQ_API_KEY` exists in this environment, but sending
business data to an external service is not something to enable without explicit instruction.
Requires: a completion function passed to `ProviderConfig(mode=MODE_CALLABLE, fn=...)`, plus
confirmation that sending this data off-machine is intended.

**Authentication.** The app sends `x-role`; a deployment puts an IdP in front. No credential
handling is built, because a fake one looks like security and is not.

Each is reported by `/health` and rendered in the app's status bar, so the operating state is
visible rather than assumed.

---

## 7. Exit criteria

- All 803 existing tests pass, unmodified.
- Phase 10 tests pass.
- Phase 10 validator: zero problems.
- Phases 7, 8, 9 validators still pass.
- Source CSVs byte-identical.
- Every quarantined integration reports exactly what it needs.
