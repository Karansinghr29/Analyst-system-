# Phase 15 — Natural-language coverage

The eight owner UAT strings are smoke tests, not the product surface. An owner may ask a
supported question in many reasonable forms. Mapping uses the existing concept map, owner-intent
classifier, question understander, conversation follow-up inheritance, Trust Gate, and planner.

No second engine, no RAG, no keyword path that skips Question Understanding.

## Rules

- Supported paraphrases resolve to the same concept/family as the canonical question.
- Genuine ambiguity (revenue vs profit for “What did we make?”; collections app vs ledger)
  returns clarification.
- Unsupported concepts return NOT_DETERMINABLE with the exact required phrase.
- Follow-ups inherit the prior subject only when concept matching finds no new subject.
- “Explain collections” after revenue does **not** inherit revenue.
- BLOCK/SHOW_BOTH posture is a function of the resolved metric, not of wording.
- A bare follow-up after a whole-business workflow repeats that workflow
  (`resolve_owner_intent`).

See `tests/test_phase15_nl_coverage.py` for the evaluation suite.
