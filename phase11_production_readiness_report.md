# Phase 11 Production Readiness Report

**Date:** 2026-09-02
**Scope:** Activation of live data, production LLM, and authentication/authorization
boundaries, plus security and observability. Phases 1–10 are unchanged in architecture.

This report does **not** claim production completion because connectors exist.
Each boundary is TRUSTED only if it is actually enforced and has passed its gate;
otherwise it is QUARANTINED with a named remaining requirement.

---

## 1. Integrity

| Item | Result |
|---|---|
| Source CSV SHA-256 | `aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26` (baseline match) |
| Metric definitions / trust levels | Unchanged. No owner decision recorded. |
| Engine / trust gate / verbalization guard | Unchanged. |

---

## 2. Boundary status

### 2.1 Live Supabase / production data — **QUARANTINED**

The read-only connector is implemented (`SupabaseRestTransport`, `PostgresReadOnlyTransport`).
There is no write method. Logical names map from `evidence/file_manifest.csv`.
`RevalidationHarness` now compares live schema/row counts to the export, replays the
80 checks / 12 conflicts / 32 DQ findings, and will re-execute all 49 metrics against
live rows **only** after schema/row-count match (overlay). Bind still requires a pass.

This process was **not** given a live read-only URL/key and as-of date with
`AI_ANALYTICS_LIVE_ENABLE=true`, so no live bind was attempted and no live rows were
fetched. The trusted **export** continues to serve.

**Remaining requirement:** set `AI_ANALYTICS_LIVE_ENABLE=true`, supply
`SUPABASE_URL` + `SUPABASE_READONLY_KEY` (or `DATABASE_URL`) and
`AI_ANALYTICS_LIVE_AS_OF`, run the harness against live rows, and record an owner
decision for every row-count, schema, conflict, trust, or validation divergence.
Until that pass, live data must not serve the engine.

### 2.2 Production LLM — **QUARANTINED**

`OpenAICompatibleProvider` exists behind `ProviderConfig`. Construction requires
`AI_ANALYTICS_LLM_ENABLE=true` plus mode/adapter/credential. A key in the environment
is not consent. Default remains `DeterministicMockProvider`. Anthropic remains a
shape only.

The production-path adversarial suite runs against a hostile `CallableProvider` on
the same `LLMInterface` + verbalization guard a live adapter would sit behind. Tests
do not send business data to an external model.

**Remaining requirement:** set `AI_ANALYTICS_LLM_ENABLE=true`,
`AI_ANALYTICS_LLM_MODE=http`, adapter name, endpoint, and key, with an explicit
decision that this dataset may leave the machine. Then re-run the adversarial suite
against that deployment.

### 2.3 Authentication + authorization — **ENFORCED**

`x-role` is not identity. `/api/*` requires a Bearer token verified by
`IdentityVerifier`. Default without `AI_ANALYTICS_AUTH_SECRET` is
`FailClosedAuthenticator` (every API call 401). With the secret, HMAC bearer tokens
are accepted; an IdP attaches by supplying a verifier.

Authorization still only filters which metrics are listed. Trust levels are
re-read from the gate. Conversations are isolated by `subject`. Cross-role
workspaces 404. Tenant/property claims cannot widen access.

`/health` reports auth `TRUSTED` when a verifier is configured, `QUARANTINED`
when fail-closed (enforcement is still on; remaining requirement is a secret or IdP).

Tests inject the HMAC test authenticator. They do not invent a login UI.

**Remaining requirement for a named IdP:** pass an `IdentityVerifier` from the
deployment’s identity provider. HMAC is a stand-in, not a substitute for SSO.

### 2.4 Security — **in place**

CORS allowlist (wildcard refused in production), security headers, ask-body length
cap, in-memory rate-limit hook, error sanitization, secret-material scan on API
response bodies. Frontend `api.js` sends `Authorization`, not `x-role`.

### 2.5 Observability — **in place**

`X-Request-ID` on every response. JSON audit lines without question/answer/values/
tokens/SQL. Counters for trust postures, source quarantine, LLM fallback, HTTP
401/429. Ask audits carry `metric_ids`, intent, trust level, outcome, fallback.

---

## 3. What Phase 11 did not do

- Did not modify source CSVs.
- Did not change metric definitions or trust levels.
- Did not write to production business tables.
- Did not send production business data to an external model.
- Did not claim the live source or production LLM is complete.

---

## 4. Verification (2026-09-02)

| Gate | Result |
|---|---|
| Source CSV SHA-256 | Matches baseline `aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26` |
| `pytest` (Phases 1–11) | **894 passed** |
| `validate_phase7_consistency.py` | 0 problems |
| `validate_phase8_consistency.py` | 0 problems |
| `validate_phase9_consistency.py` | 0 problems (export revalidation 80/80, 12/12, 32/32) |
| `validate_phase10_consistency.py` | 0 problems |
| `validate_phase11_consistency.py` | 0 problems |
| `phase11_evaluation.csv` | 17/17 PASS |

Phase 11 is **activation-complete with honest quarantine** for live data and the production LLM. Authentication is actually enforced. The export engine path remains the serving path. Connectors existing is not a pass of the live or LLM gates.
