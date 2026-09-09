"""
insight_ranker.py -- Phase 5. Ranking exactly per insight_generation_spec.md 4.

    "Candidates are ranked ... using a strict priority ordering -- **not a blended numeric
     score** (a blended score would itself be an invented metric, the same failure mode
     analytics_execution_spec.md 2.8 already prohibits for risk-scan composites)"

The four dimensions, in the spec's own order:

  1. Trust-adjusted severity. "A CRITICAL DQ finding on a SAFE-adjacent, currently-live exposure
     ranks above an anomaly on an already-SHOW_BOTH/BLOCK metric (whose ambiguity is already
     fully disclosed and therefore less 'newly actionable')."
  2. Recency of the underlying evidence.
  3. Materiality (Rs. amount or % scale) as a TIEBREAKER WITHIN the same severity tier.
  4. Coverage sufficiency -- an under-6-month domain is never ranked as a trend insight.

They are compared lexicographically and never combined. `explain_ranking()` returns each
dimension separately so a reviewer can see why one insight outranked another, rather than
being handed a number that hides it.
"""
from engine.insight_models import RankingDimensions, NOT_DETERMINABLE_TEXT

# Dimension 1. Lower sorts first. The two-part structure encodes 4's own rule: severity is the
# primary key, but an already-disclosed SHOW_BOTH/BLOCK ambiguity is demoted WITHIN its severity
# because it is "less newly actionable" -- the spec's words, not a judgement added here.
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 2, "MEDIUM": 4, "LOW": 6, "INFORMATIONAL": 8}
ALREADY_DISCLOSED_PENALTY = 1     # keeps the finding inside its severity tier, below its peers

# Dimension 2. Lower sorts first. The exported evidence is a single static snapshot, so there is
# no "newly true this cycle" signal available -- every standing finding is equally recent, and
# claiming otherwise would invent state the evidence does not contain. Recency therefore
# distinguishes only what the evidence CAN distinguish: a condition re-derived live from a
# current diagnostic (trigger 4) is more freshly established than a finding transcribed once
# into the DQ register.
RECENCY_LIVE_REDERIVED = 0
RECENCY_STANDING_FINDING = 1


def severity_rank(severity, trust_level, already_disclosed=False):
    base = SEVERITY_ORDER.get((severity or "").upper(), 5)
    if already_disclosed or trust_level in ("SHOW_BOTH", "BLOCK"):
        return base + ALREADY_DISCLOSED_PENALTY
    return base


def build_dimensions(severity, trust_level, materiality_amount, materiality_note,
                     coverage_sufficient, live_rederived=False, already_disclosed=False):
    return RankingDimensions(
        trust_adjusted_severity=severity_rank(severity, trust_level, already_disclosed),
        recency=RECENCY_LIVE_REDERIVED if live_rederived else RECENCY_STANDING_FINDING,
        materiality_amount=materiality_amount,
        materiality_note=materiality_note or (
            NOT_DETERMINABLE_TEXT if materiality_amount is None else ""),
        coverage_sufficient=coverage_sufficient,
    )


def rank(insights):
    """Deterministic ordering. Ties beyond the four documented dimensions are broken by
    insight_id so the same candidate set always produces the same sequence -- required by
    ai_analytics_architecture.md 9's determinism rule, and by the Phase 5 brief's
    'insight ranking determinism' test."""
    return tuple(sorted(insights, key=lambda i: (i.ranking.sort_key(), i.insight_id)))


def explain_ranking(insight):
    """The four dimensions, separately. Never a single score."""
    r = insight.ranking
    return {
        "1_trust_adjusted_severity": r.trust_adjusted_severity,
        "2_recency": ("live re-derived" if r.recency == RECENCY_LIVE_REDERIVED
                      else "standing finding"),
        "3_materiality": (r.materiality_amount if r.materiality_amount is not None
                          else r.materiality_note or NOT_DETERMINABLE_TEXT),
        "4_coverage_sufficient": r.coverage_sufficient,
        "note": ("insight_generation_spec.md 4: these dimensions are compared "
                 "lexicographically and are never blended into one score."),
    }


def group_by_dimension(insights):
    """Preserve the dimensions separately when presenting a ranked list, per the Phase 5 brief:
    'If multiple ranking dimensions exist, preserve them separately.'"""
    out = {}
    for i in insights:
        out.setdefault(i.ranking.trust_adjusted_severity, []).append(i)
    return {k: tuple(v) for k, v in sorted(out.items())}
