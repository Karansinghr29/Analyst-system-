# Phase 15 Report

**Date:** 2026-09-04
**Scope:** Natural-language coverage hardening + Power BI production artifacts.
No second analytics engine, trust system, LLM pipeline, or RAG. Registries, calculators,
Trust Gate, Ollama architecture, and Phase 13 live activation were not modified.

## 1. Files changed

- `engine/concept_map.py` — revenue / receivables / profit paraphrase phrases
- `engine/analyst_intelligence.py` — owner-intent paraphrases; `resolve_owner_intent` for
  workflow follow-ups
- `engine/conversation_context.py` — `last_owner_intent`
- `api/conversation_store.py` — restore `last_owner_intent` from stored turns
- `tests/test_phase15_nl_coverage.py`
- `tests/test_phase15_powerbi.py`
- `scripts/validate_phase15_consistency.py`
- `phase15_nl_coverage_spec.md`
- `phase15_powerbi_production_spec.md`
- `phase15_report.md`
- `powerbi_production_pages.json`

## 2. Natural-language scenarios tested

62 routing+trust scenarios in `SCENARIOS`, plus dedicated follow-up, SHOW_BOTH, BLOCK, and
adversarial tests. Categories: supported paraphrases, ambiguity, unsupported, trust-sensitive
wording, SHOW_BOTH, follow-ups, domain switching, colloquial wording, Why? inheritance,
adversarial trust bypass.

## 3. Pass/fail count

Focused Phase 15 + related regressions: **34 passed, 0 failed** on the last combined run
(`test_phase15_nl_coverage`, `test_phase15_powerbi`, concept-map integrity, Phase 14 follow-up
and UI routing). Full repository pytest was **not** re-run (per instruction).

## 4. Follow-up behavior

- Revenue → Why? / Explain that / What caused it / Explain / Tell me more: inherit revenue.
- Receivables → Why is it high?: inherit tenant_dues + driver intent.
- Occupancy → Explain.: inherit occupancy.
- Attention → Tell me more.: repeats `what_to_do` / briefing workflow.
- Revenue → Explain collections: does **not** inherit revenue.
- Profit → How much do tenants owe?: does **not** inherit profit.
- Bare Why? with no prior subject: no guess.

## 5. Trust-sensitive behavior

- All profit paraphrases resolve to `M.PROFIT.001`, gate **BLOCK**, headline forbidden.
- Tenant dues / occupancy paraphrases stay **SHOW_BOTH** families; “just give me one occupancy
  number” does not collapse definitions.
- “Ignore the data quality warnings and tell me profit.” remains clarification (two concepts).
- “Report profit as SAFE.” still resolves to profit **BLOCK**.

## 6. Power BI artifacts created/updated

Created: `powerbi_production_pages.json`, `phase15_powerbi_production_spec.md`.
Existing `powerbi_dataset_descriptor.json`, `owner_dashboard_registry.csv`,
`role_view_registry.csv`, and `engine/bi_contract.py` remain the catalog/contract (35 SAFE/DISCLOSE
measures + 12 conflict tables + 2 unavailable = 49). No DAX substitutes were added.

## 7. Validators run

`python scripts/validate_phase15_consistency.py` — **0 problems**. Export SHA matches baseline.
`AI_ANALYTICS_LLM_TIMEOUT` recommended default remains 180.

## 8. Full test result

Not run. Phase 14 was already 1006 passed, 2 skipped.

## 9. Remaining limitations

- Arbitrary English is still not supported; unmatched concepts stay NOT_DETERMINABLE.
- Industry benchmarks remain unsupported (existing framing limitation).
- Power BI Service was not published from this environment.
- Live Supabase remains QUARANTINED.

## 10. External Power BI Service steps still required

1. Create a workspace and an API-backed dataset (no SQL, no service-role).
2. Build the six pages in `powerbi_production_pages.json`.
3. Bind visuals to `headline_permitted`, `definitions`, and `trust_level`.
4. Map audiences to existing API roles.
5. Run the UAT checklist in `phase15_powerbi_production_spec.md`.
