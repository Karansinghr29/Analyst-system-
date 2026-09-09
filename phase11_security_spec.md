# Phase 11 Security Spec

## 1. Surface

All rules apply to the FastAPI adapter in `api/service.py`. The engine is unchanged.

## 2. CORS

`AI_ANALYTICS_CORS_ORIGINS` is a comma-separated allowlist. Empty (default) means
same-origin only — the app is served from the same origin as the API. A wildcard is
refused in production (`AI_ANALYTICS_ENV=production`).

## 3. Headers

Every response:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Cache-Control: no-store` on `/api/*` (trust must not be cached)
- `X-Request-ID` (incoming or generated)

## 4. Request validation

Unchanged input surface: identifiers, catalogued dimensions, natural-language
question. No filter language, formula, or query parameter. Ask body is length-capped
(`AI_ANALYTICS_MAX_QUESTION_CHARS`, default 4000).

## 5. Rate limiting

Hook: `RateLimiter.allow(identity_or_ip)`. Default in-memory token bucket.
`429` when exceeded. Tests may inject a disabled limiter. This is a hook a
deployment can replace; it is not a distributed limiter.

## 6. Error sanitization

HTTP error bodies never include: filesystem paths, SQL, env var names with values,
API keys, connection strings, stack traces, evidence filenames. Internal detail is
audit-logged under the request id only.

## 7. Secrets

- No credential is read at import time (Phase 9 rule, kept)
- Responses are scanned for the configured secret material; a hit is a 500 and an
  audit event, not a leaked body
- Frontend must not receive keys, SQL, or source paths (existing payload prohibition)

## 8. Prompt injection / API abuse

Covered by the LLM adversarial suite and by: oversized bodies, unauthenticated
flood (rate limit), and header spoofing (`x-role` ignored).
