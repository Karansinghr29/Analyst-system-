# Phase 11 Authentication and Authorization Spec

## 1. Split

- **Authentication** answers "who is this request?"
- **Authorization** answers "which metrics may this identity's role see?"

Authorization already exists (`api/authorization.py`). It must not grow a trust
mechanism. Authentication is new. It must not choose a trust level.

## 2. Identity

An `Identity` is produced only by an `IdentityVerifier` that the deployment supplies
(or by the built-in HMAC verifier when `AI_ANALYTICS_AUTH_SECRET` is set).

```
subject          IdP user id (audit only; entitlements do not attach to it)
role_id          must be a known role (owner or an analyst lens)
tenant_id        optional; empty in this export (single organization)
property_id      optional; empty — property grain is degenerate (one property)
```

`Session` is derived from `Identity`. The HTTP layer never reads `x-role` to decide
access.

## 3. Verifier interface (provider-independent)

```
IdentityVerifier.verify(token: str) -> Identity
```

A deployment attaches an IdP by passing a verifier into `BearerAuthenticator`. This
codebase does not store passwords, issue cookies, or implement an IdP.

Built-in: HMAC-signed bearer tokens (`sub`, `role`, `exp`, optional `tenant_id` /
`property_id`). An IdP that can mint the same shape, or a custom `verify()` callable,
is a drop-in.

## 4. Fail-closed default

If no verifier and no `AI_ANALYTICS_AUTH_SECRET` are configured:

- `GET /health`, `GET /`, `GET /static/*` remain reachable (operators must see quarantine)
- every `/api/*` route returns 401
- remaining requirement is named on `/health`

This is real enforcement, not a fake login screen.

## 5. Authorization rules

- Role → visible metrics: existing `Authorizer.filter_metrics`
- A role never receives a looser trust posture
- `owner_home`, insights, and changes are filtered to the identity's visible metrics
- Metric detail / conflict for a non-visible metric stays "not available" (no existence probe via 403)
- `/api/ask` refuses to return figures for metrics the role may not see
- Conversations are isolated by `subject`: another subject's id is 404
- `x-role` / `x-subject` are ignored even if present
- Tenant/property claims, when present, cannot widen access; this dataset has one org and one property, so isolation is structural rather than a second filter invented here

## 6. Tests required

Unauthorized request → 401.
Spoofed `x-role` without a token → 401.
Known token, unknown role → 403.
Financial analyst must not receive an Operations-only metric figure.
Conversation of subject A is 404 for subject B.
Direct `/api/metrics/{id}` bypass uses the same filter as the listing.
Authorizer still exposes no trust API.
