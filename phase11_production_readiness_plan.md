# Phase 11 Production Readiness Plan

Activation of the three quarantined production boundaries, without redesigning or
weakening Phases 1–10.

---

## 1. What this phase is

Phase 11 does **not** add a second engine, a second trust gate, or a second analytics
path. It activates the plugs Phase 9 already built:

| Boundary | Phase 9 plug | Phase 11 activation |
|---|---|---|
| Live data | `DataSource` + `RevalidationHarness` + `bind_source` | Read-only Supabase/Postgres connector. Bind only after the harness passes against live rows |
| LLM | `ProviderConfig` + `CallableProvider` / HTTP **shapes** | Real HTTP adapter behind explicit enable. Still untrusted; still guarded |
| Auth | `Session` + `Authorizer` (role filter) | Authenticated identity required. Role comes from the identity, never from `x-role` |

Connectors existing is **not** completion. Completion requires: live source passed
revalidation **or** honestly QUARANTINED; authentication actually enforced; production
LLM path passed the adversarial suite **or** honestly QUARANTINED.

---

## 2. Non-negotiable invariants (unchanged)

Every Phase 9/10 invariant still holds. Phase 11 adds none that contradict them.

- No business logic outside the engine
- BLOCK exposes no headline; SHOW_BOTH keeps every definition; NOT_DETERMINABLE keeps the exact phrase
- Trust is never cached and never per-user
- LLM stays untrusted; verbalization guard is binding
- Source CSVs remain byte-identical (`SHA-256 aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26`)
- No live database modification
- Metric definitions and trust levels change only via a recorded owner decision

---

## 3. Build order

1. **AuthN** — fail-closed by default, so later HTTP work cannot ship an open door
2. **Security + observability** — wrap the existing FastAPI adapter
3. **Live connector + harness extension** — still cannot bind without a pass
4. **LLM HTTP adapter** — explicit enable; default remains the offline mock
5. **Frontend** — stop sending `x-role` as authority; send `Authorization`
6. **Validator + tests + readiness report**

---

## 4. Honest quarantine

If a credential or configuration is missing, that component stays QUARANTINED and
`/health` names the exact remaining requirement. The system continues to serve the
export, the offline LLM, and authenticated-or-rejected HTTP — it does not pretend
the missing piece is on.

---

## 5. Exit criteria

- Phase 1–10 tests still pass
- Phase 11 tests pass
- `scripts/validate_phase11_consistency.py` reports zero problems
- Source CSVs byte-identical
- `/health` reports each of data / LLM / auth as TRUSTED or QUARANTINED with a remaining requirement
- No claim of live-data completion unless `bind_source` accepted a live source after a harness pass
