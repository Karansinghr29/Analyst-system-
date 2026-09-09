"""
insight_engine.py -- Phase 5. The Insight Generator role (ai_agent_roles.md 2), implementing
insight_generation_spec.md's proactive flow:

    Trigger -> Candidate Generation -> Ranking -> Answer Contract Assembly -> Delivery

Scope, stated honestly and up front
-----------------------------------
insight_generation_spec.md 2 defines exactly four triggers and says "no other trigger source is
in scope". Two of the four have firing conditions the specifications DELIBERATELY decline to
fix:

  * Condition 2 (anomaly): analytics_execution_spec.md 2.5 -- "the specific statistical method
    is an implementation-phase decision, not fixed by this specification."
  * Condition 3 (material delta): insight_generation_spec.md 2 -- "this specification does not
    fix the threshold value (an implementation-phase/business decision)."

No threshold for either exists anywhere in the exported evidence or the specification set. This
engine therefore does NOT fire those two triggers, and reports them as
"Not determinable from exported evidence." rather than inventing a cutoff. Inventing one would
be the same class of violation as inventing a metric: every insight produced under it would be
an artifact of a number this project made up. `unsupported_triggers()` surfaces this so the gap
is visible in the evaluation report rather than looking like zero findings.

The two implementable triggers, plus the conflict case 5 permits, are:

  1. Condition 1 -- CRITICAL/HIGH DQ findings (data_quality_registry.csv's severity column).
  4. Condition 4 -- a documented risk boundary currently crossed. The boundary is the
     diagnostic's OWN definition, so a non-empty result set IS the crossing; no threshold is
     introduced.
  5 -- a BLOCK/SHOW_BOTH metric may generate an insight about the CONFLICT itself, never one
     asserting a competing figure as the business's actual position.
"""
import csv
import os

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.execution import MetricExecutor
from engine import insight_explanations as expl
from engine import insight_ranker
from engine.insight_models import (
    Insight, NOT_DETERMINABLE_TEXT, UNSPECIFIED_TRIGGERS, classify_area,
    TRIGGER_DQ_SEVERITY, TRIGGER_RISK_BOUNDARY, TRIGGER_DEFINITION_CONFLICT,
    TRIGGER_ANOMALY, TRIGGER_MATERIAL_DELTA, CLASS_DEFINITION_CONFLICT,
)

# The package root, derived from this file's location rather than from the absolute path of
# the machine the export was built on -- that path is correct exactly once, on that machine,
# and a deployed copy of the same package sits somewhere else. `AI_ANALYTICS_BASE` overrides
# it where a deployment mounts the evidence elsewhere. The evidence itself is unchanged.
BASE = os.environ.get("AI_ANALYTICS_BASE") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
DQ_REGISTRY_PATH = os.path.join(BASE, "data_quality_registry.csv")

# 2 condition 1: "A CRITICAL or HIGH-severity DQ finding exists ... Per data_quality_report.md's
# own final tally: 4 CRITICAL, 8 HIGH. Each is a standing candidate."
PROACTIVE_SEVERITIES = ("CRITICAL", "HIGH")

# 2 condition 4's named examples, plus the other diagnostics of the same shape already in the
# registry. Each is a metric whose non-empty result set IS the documented boundary crossing.
RISK_BOUNDARY_METRICS = ("M.RISK.004", "M.RISK.005", "M.RISK.006", "M.RISK.007")

# 5: BLOCK/SHOW_BOTH concepts whose disagreement is itself the insight.
CONFLICT_CONCEPTS = (
    ("tenant dues", ("M.AR.001A", "M.AR.001B", "M.AR.001C", "M.AR.001D")),
    ("profit", ("M.PROFIT.001",)),
    ("occupancy", ("M.OCC.001",)),
    ("owner rent", ("M.OWN.002",)),
)


class InsightEngine:
    def __init__(self, registry: SemanticRegistry = None, gate: TrustGate = None,
                 executor: MetricExecutor = None, dq_path=DQ_REGISTRY_PATH):
        self.registry = registry or SemanticRegistry()
        self.gate = gate or TrustGate(self.registry)
        self.executor = executor or MetricExecutor(registry=self.registry, gate=self.gate)
        self.dq_rows = self._load_dq(dq_path)

    @staticmethod
    def _load_dq(path):
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    # -- the public surface ---------------------------------------------------------------------

    def generate(self, include_conflicts=True, include_risk_boundaries=True):
        """Produce ranked insight candidates. Every candidate must reach OBSERVATION
        (insight_generation_spec.md 3); those that do not are dropped and counted, never padded
        out to look like findings."""
        candidates = []
        candidates.extend(self._from_dq_severity())
        if include_risk_boundaries:
            candidates.extend(self._from_risk_boundaries())
        if include_conflicts:
            candidates.extend(self._from_conflicts())

        kept = [c for c in candidates if c.reached_observation]
        return insight_ranker.rank(kept)

    @staticmethod
    def unsupported_triggers():
        """The two triggers whose thresholds the specifications leave open. Returned so the
        evaluation report shows the gap explicitly rather than reporting zero findings as if
        none existed."""
        return dict(UNSPECIFIED_TRIGGERS)

    # -- trigger 1: DQ severity ------------------------------------------------------------------

    def _from_dq_severity(self):
        out = []
        for row in self.dq_rows:
            severity = (row.get("severity") or "").upper()
            if severity not in PROACTIVE_SEVERITIES:
                continue

            dq_id = row.get("dq_id", "")
            metric_ids = self._metrics_for_dq(dq_id)
            trust = self._dq_trust(row, metric_ids)

            ladder = expl.build_dq_ladder(row, metric_ids, trust)
            amount = expl.parse_amount(row.get("affected_amount"))
            count = expl.parse_count(row.get("affected_rows"))

            recommendation = self._dq_recommendation(row, trust, dq_id)

            out.append(Insight(
                insight_id=f"INS.DQ.{dq_id}",
                insight_class=classify_area(row.get("business_area")),
                trigger=TRIGGER_DQ_SEVERITY,
                trigger_metric_ids=metric_ids,
                fact=ladder["fact"], calculation=ladder["calculation"],
                observation=ladder["observation"], inference=ladder["inference"],
                hypothesis=ladder["hypothesis"], recommendation=recommendation,
                trust_level=trust, confidence=ladder["confidence"],
                caveat=self._caveat_for(metric_ids),
                dq_ids=(dq_id,),
                conflict_ids=self._conflicts_for(metric_ids),
                evidence_sources=tuple(
                    e.strip() for e in (row.get("evidence_files") or "").split(";") if e.strip()),
                time_period="standing condition as at the export snapshot (2026-08-29)",
                business_dimension=row.get("business_area", ""),
                affected_amount=amount, affected_count=count,
                limitations=("" if amount is not None else
                             f"No numeric exposure is recorded for {dq_id} in "
                             f"data_quality_registry.csv. {NOT_DETERMINABLE_TEXT}"),
                headline_permitted=False,
                ranking=insight_ranker.build_dimensions(
                    severity=severity, trust_level=trust, materiality_amount=amount,
                    materiality_note=(row.get("affected_amount") or "")[:120],
                    coverage_sufficient=expl.trend_permitted(metric_ids),
                    live_rederived=False,
                ),
            ))
        return out

    def _dq_recommendation(self, row, trust, dq_id):
        """business_reasoning_spec.md 2: a recommendation touching a BLOCK metric must recommend
        RESOLVING THE CONFLICT, never an operational action on a disputed figure. For other
        findings, the recommendation is bounded by what the registry itself records as fixable."""
        offline = (row.get("offline_fix_possible") or "").strip()
        live = (row.get("live_db_required") or "").strip()
        if trust == "BLOCK":
            return (f"Recommend an owner decision resolving the definitional conflict behind "
                    f"{dq_id} before any figure it affects is used for a decision. This is a "
                    f"recommendation, not a certainty.")
        if live and live.lower().startswith(("yes", "required", "true")):
            return (f"Recommend confirming {dq_id} against a live database, since the exported "
                    f"evidence cannot establish the current state. This is a recommendation, "
                    f"not a certainty.")
        if offline and offline.lower().startswith(("yes", "true")):
            return (f"Recommend remediating {dq_id} using the exported evidence, which the "
                    f"registry records as sufficient for an offline fix. This is a "
                    f"recommendation, not a certainty.")
        return (f"Recommend reviewing {dq_id} with its documented evidence before relying on "
                f"the metrics it affects. This is a recommendation, not a certainty.")

    # -- trigger 4: documented risk boundary -----------------------------------------------------

    def _from_risk_boundaries(self):
        out = []
        for mid in RISK_BOUNDARY_METRICS:
            if mid not in self.registry:
                continue
            spec = self.registry.get(mid)
            decision = self.gate.authorize(mid)
            answer = self.executor.execute(mid)
            if not answer.results:
                continue

            r = answer.results[0]
            crossed, count, amount = self._boundary_crossed(r.value)
            if not crossed:
                continue      # the condition is not currently true; no candidate, no padding

            ladder = expl.build_risk_boundary_ladder(
                mid, spec.semantic_name, r.value, r.unit, spec.caveat_text, r.validation_status)

            out.append(Insight(
                insight_id=f"INS.RISK.{mid}",
                insight_class=classify_area(spec.domain + " " + spec.semantic_name),
                trigger=TRIGGER_RISK_BOUNDARY,
                trigger_metric_ids=(mid,),
                fact=ladder["fact"], calculation=ladder["calculation"],
                observation=ladder["observation"], inference=ladder["inference"],
                recommendation=(
                    f"Recommend reviewing the {spec.semantic_name} worklist and confirming "
                    f"whether each row requires remediation. This is a recommendation, not a "
                    f"certainty."),
                trust_level=decision.effective_level,
                confidence=answer.confidence,
                caveat=spec.caveat_text,
                conflict_ids=spec.conflict_ids, dq_ids=spec.dq_ids,
                evidence_sources=tuple(r.evidence_sources),
                time_period=r.as_of,
                business_dimension=spec.domain,
                affected_amount=amount, affected_count=count,
                limitations=r.limitations,
                headline_permitted=decision.headline_permitted,
                ranking=insight_ranker.build_dimensions(
                    severity=self._severity_for_metric(mid),
                    trust_level=decision.effective_level,
                    materiality_amount=amount,
                    materiality_note="" if amount is not None else NOT_DETERMINABLE_TEXT,
                    coverage_sufficient=expl.trend_permitted((mid,)),
                    live_rederived=True,       # re-derived from the diagnostic just now
                ),
            ))
        return out

    @staticmethod
    def _boundary_crossed(value):
        """A non-empty diagnostic result IS the documented boundary crossing (2 condition 4).
        Returns (crossed, count, amount). No threshold is introduced anywhere here."""
        if isinstance(value, bool):
            return value, None, None
        if isinstance(value, (int, float)):
            return value > 0, (int(value) if float(value).is_integer() else None), None
        if isinstance(value, dict):
            count = None
            amount = None
            for k, v in value.items():
                kl = str(k).lower()
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    if "amount" in kl or "value" in kl or "total" in kl:
                        amount = float(v)
                    elif count is None and ("count" in kl or "rows" in kl or "groups" in kl):
                        count = int(v)
            nonzero = any(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0
                          for v in value.values())
            return nonzero, count, amount
        return False, None, None

    def _severity_for_metric(self, metric_id):
        """Severity comes from the DQ register the metric carries, never assigned here."""
        spec = self.registry.get(metric_id)
        best = "LOW"
        order = ("INFORMATIONAL", "LOW", "MEDIUM", "HIGH", "CRITICAL")
        for row in self.dq_rows:
            if row.get("dq_id") in spec.dq_ids:
                sev = (row.get("severity") or "").upper()
                if sev in order and order.index(sev) > order.index(best):
                    best = sev
        return best

    # -- 5: conflict insights -----------------------------------------------------------------

    def _from_conflicts(self):
        out = []
        for label, metric_ids in CONFLICT_CONCEPTS:
            head = metric_ids[0]
            if head not in self.registry:
                continue
            decision = self.gate.authorize(head)
            if decision.effective_level not in ("SHOW_BOTH", "BLOCK"):
                continue

            answer = self.executor.execute(head)
            definitions = tuple((r.definition_label, r.value) for r in answer.results)
            if len(definitions) < 2:
                continue

            spread = ""
            if answer.numeric_difference:
                pair, diff = next(iter(answer.numeric_difference.items()))
                spread = (f"{pair} differ by {diff['absolute_difference']}"
                          + (f" ({diff['percentage_difference']}%)"
                             if diff.get("percentage_difference") is not None else ""))

            family = tuple(decision.required_definitions) or tuple(metric_ids)

            # The insight covers the WHOLE family, so its trust level is the family's worst --
            # not the head member's. metric_dependency_graph.md 7: "EVERY composite KPI inherits
            # the WORST trust level of its inputs." The AR family is the case that matters: Defs
            # A/B are SHOW_BOTH while C/D are BLOCK, so taking the head's SHOW_BOTH would
            # present a BLOCK-severity conflict as merely "two views to compare", understating
            # a ~120x disagreement the trust policy refuses to let anyone state a number for.
            family_trust = self._worst_trust([m for m in family if m in self.registry])

            ladder = expl.build_conflict_ladder(
                label, list(family), definitions, spread, decision.required_disclosures)

            out.append(Insight(
                insight_id=f"INS.CONFLICT.{head}",
                insight_class=CLASS_DEFINITION_CONFLICT,
                trigger=TRIGGER_DEFINITION_CONFLICT,
                trigger_metric_ids=family,
                fact=ladder["fact"], calculation=ladder["calculation"],
                observation=ladder["observation"], inference=ladder["inference"],
                recommendation=ladder["recommendation"],
                trust_level=family_trust,
                confidence=answer.confidence,
                caveat=answer.caveat,
                conflict_ids=answer.conflict_ids, dq_ids=answer.dq_ids,
                evidence_sources=tuple(
                    e for r in answer.results for e in r.evidence_sources)[:12],
                time_period=answer.as_of,
                business_dimension=self.registry.get(head).domain,
                affected_amount=None,
                affected_count=len(definitions),
                limitations=("The competing figures are shown per definition. No single value "
                             "for this concept exists in the exported evidence "
                             "(insight_generation_spec.md 5)."),
                headline_permitted=False,
                ranking=insight_ranker.build_dimensions(
                    severity=self._severity_for_metric(head),
                    trust_level=decision.effective_level,
                    materiality_amount=None,
                    materiality_note="Spread stated per definition; no single amount exists.",
                    coverage_sufficient=expl.trend_permitted(metric_ids),
                    live_rederived=True, already_disclosed=True,
                ),
            ))
        return out

    # -- helpers ----------------------------------------------------------------------------------

    def _metrics_for_dq(self, dq_id):
        """Which registry metrics carry this dq_id. Read from the registry, never guessed from
        the DQ row's free-text `metrics_affected` column (which names concepts, not ids)."""
        return tuple(m for m in self.registry.all_ids()
                     if dq_id in self.registry.get(m).dq_ids)

    _TRUST_SEVERITY = {"SAFE": 0, "DISCLOSE": 1, "SHOW_BOTH": 2, "NOT_DETERMINABLE": 3,
                       "BLOCK": 4}

    def _dq_trust(self, row, metric_ids):
        """Trust posture for a DQ-triggered insight.

        The DQ register carries its OWN `ai_handling` column, which is the documented handling
        for that finding, and it is authoritative here. Two problems, both found by running the
        engine, make the metric-derived posture insufficient on its own:

          * Some findings are carried by NO registry metric (DQ.001 appears in no metric's
            dq_ids). Deriving trust purely from metrics returned the SAFE default -- the most
            permissive posture -- for a CRITICAL finding whose own ai_handling is BLOCK.
          * Worst-of-metrics can be misleading in the other direction: DQ.004's occupancy
            metrics include the bed-grain M.OCC.003, which is NOT_DETERMINABLE for an unrelated
            reason (no exported reference), so the occupancy insight was labelled
            NOT_DETERMINABLE when the register records it as SHOW_BOTH.

        Taking the WORST of the documented handling and the metrics' own gate verdicts keeps
        both sources honest and can only tighten, never loosen.
        """
        declared = (row.get("ai_handling") or "").strip().upper()
        worst = declared if declared in self._TRUST_SEVERITY else ""

        for m in metric_ids:
            lv = self.gate.authorize(m).effective_level
            if not worst or self._TRUST_SEVERITY[lv] > self._TRUST_SEVERITY[worst]:
                worst = lv

        if not worst:
            # Neither the register nor any metric states a posture. Never fall back to SAFE:
            # an unstated posture is unverified, not permissive.
            return "NOT_DETERMINABLE"
        return worst

    def _worst_trust(self, metric_ids):
        worst = "SAFE"
        for m in metric_ids:
            lv = self.gate.authorize(m).effective_level
            if self._TRUST_SEVERITY[lv] > self._TRUST_SEVERITY[worst]:
                worst = lv
        return worst

    def _caveat_for(self, metric_ids):
        for m in metric_ids:
            c = self.registry.get(m).caveat_text
            if c.strip():
                return c
        return ""

    def _conflicts_for(self, metric_ids):
        out = []
        for m in metric_ids:
            for c in self.registry.get(m).conflict_ids:
                if c not in out:
                    out.append(c)
        return tuple(out)
