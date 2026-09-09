"""
executive_summary.py -- Phase 6. The management briefing: what the owner sees on opening the
system, without asking anything.

Every line in it is an ANSWER, and insight_generation_spec.md 1 already settled what that
means: "an insight is not a different KIND of output, it is an answer the system generated
without being asked, and it must satisfy every requirement a reactive answer does."

So the briefing enforces the same three rules the reactive path does, and the Phase 6 brief
restates them:

    SHOW_BOTH        -> show both definitions
    BLOCK            -> no single headline number
    NOT_DETERMINABLE -> exactly "Not determinable from exported evidence."

A KPI that cannot be shown safely is still LISTED, with the reason. Omitting it would let a
briefing read as "nothing to report here" when the truth is "this cannot be reported as one
number" -- which is the opposite of what an owner needs to know.
"""
from dataclasses import dataclass, field

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.execution import MetricExecutor
from engine.insight_engine import InsightEngine
from engine.change_detection import ChangeDetector, COMPARABLE_MONTHLY_METRICS
from engine.root_cause import RootCauseAnalyzer
from engine.result import NOT_DETERMINABLE_TEXT

# --- The briefing's own section structure, from the Phase 6 brief 7 ----------------------------

SECTION_BUSINESS_HEALTH = "BUSINESS HEALTH"
SECTION_OPERATIONS = "OPERATIONS"
SECTION_RISKS = "RISKS"
SECTION_ATTENTION = "ATTENTION REQUIRED"
SECTION_WHAT_CHANGED = "WHAT CHANGED"
SECTION_WHY = "WHY"
SECTION_WHAT_TO_DO = "WHAT TO DO"

ALL_SECTIONS = (SECTION_BUSINESS_HEALTH, SECTION_OPERATIONS, SECTION_RISKS, SECTION_ATTENTION,
                SECTION_WHAT_CHANGED, SECTION_WHY, SECTION_WHAT_TO_DO)

# The snapshot KPIs the brief enumerates, in its own order. Each is a metric_id already in the
# registry -- the briefing introduces no measure of its own.
BUSINESS_HEALTH_KPIS = (
    "M.REV.001",     # revenue
    "M.COL.001",     # collections
    "M.AR.001A",     # receivables (SHOW_BOTH family -- shown as competing definitions)
    "M.EXP.001",     # expenses
    "M.PROFIT.001",  # profit (BLOCK -- no headline)
    "M.DEP.001",     # deposits held
    "M.OWN.001",     # owner payments
    "M.CASH.001",    # cash
)

OPERATIONS_KPIS = (
    "M.OCC.001",     # occupancy (SHOW_BOTH)
    "M.TEN.001",     # staying tenants
    "M.TEN.002",     # on-notice tenants
    "M.TEN.003",     # booked beds
    "M.LIFE.002",    # move-ins
    "M.LIFE.003",    # move-outs
    "M.MAINT.001",   # maintenance volume
    "M.EB.001",      # EB / electricity
)

RISK_KPIS = (
    "M.RISK.004",    # phantom deposits
    "M.RISK.005",    # duplicate invoices
    "M.RISK.007",    # overlapping allotments
    "M.RISK.008",    # ledger/source reconciliation
)


@dataclass(frozen=True)
class KPILine:
    """One briefing line. `presentable` records whether a single figure may be shown at all."""
    metric_id: str
    display_name: str
    trust_level: str
    presentable: bool                 # False for SHOW_BOTH / BLOCK / NOT_DETERMINABLE
    value: object = None              # populated ONLY when presentable
    definitions: tuple = ()           # (label, value) pairs for SHOW_BOTH / BLOCK
    unit: str = ""
    caveat: str = ""
    conflict_ids: tuple = ()
    dq_ids: tuple = ()
    evidence_sources: tuple = ()
    as_of: str = ""
    validation_status: str = ""
    confidence: str = ""
    reason: str = ""                  # why no single figure is shown, when it is not

    def render(self):
        if self.trust_level == "NOT_DETERMINABLE":
            return f"{self.display_name}: {NOT_DETERMINABLE_TEXT} {self.reason}".strip()
        if not self.presentable:
            parts = "; ".join(f"{lab}: {val}" for lab, val in self.definitions)
            return (f"{self.display_name}: [{self.trust_level}] no single figure. "
                    f"{parts}".strip())
        line = f"{self.display_name}: {self.value} {self.unit}".rstrip()
        if self.caveat:
            line += f"  (caveat: {self.caveat[:160]})"
        return line


@dataclass
class ExecutiveSummary:
    business_health: tuple = ()
    operations: tuple = ()
    risks: tuple = ()
    attention_required: tuple = ()
    what_changed: tuple = ()
    why: tuple = ()
    what_to_do: tuple = ()
    generated_as_of: str = ""
    limitations: tuple = ()
    omitted: dict = field(default_factory=dict)

    def sections(self):
        return {
            SECTION_BUSINESS_HEALTH: self.business_health,
            SECTION_OPERATIONS: self.operations,
            SECTION_RISKS: self.risks,
            SECTION_ATTENTION: self.attention_required,
            SECTION_WHAT_CHANGED: self.what_changed,
            SECTION_WHY: self.why,
            SECTION_WHAT_TO_DO: self.what_to_do,
        }

    def populated_sections(self):
        return tuple(name for name, content in self.sections().items() if content)


class ExecutiveSummaryBuilder:
    def __init__(self, registry: SemanticRegistry = None, gate: TrustGate = None,
                 executor: MetricExecutor = None, insight_engine: InsightEngine = None,
                 detector: ChangeDetector = None, analyzer: RootCauseAnalyzer = None):
        self.registry = registry or SemanticRegistry()
        self.gate = gate or TrustGate(self.registry)
        self.executor = executor or MetricExecutor(registry=self.registry, gate=self.gate)
        self.insights = insight_engine or InsightEngine(
            registry=self.registry, gate=self.gate, executor=self.executor)
        self.detector = detector or ChangeDetector(self.registry, self.gate, self.executor)
        self.analyzer = analyzer or RootCauseAnalyzer(
            self.registry, self.gate, self.executor, self.detector)

    # -- KPI lines --------------------------------------------------------------------------------

    def kpi_line(self, metric_id):
        if metric_id not in self.registry:
            return KPILine(metric_id=metric_id, display_name=metric_id,
                           trust_level="NOT_DETERMINABLE", presentable=False,
                           reason=f"{metric_id!r} is not a semantic metric.")

        spec = self.registry.get(metric_id)
        decision = self.gate.authorize(metric_id)
        answer = self.executor.execute(metric_id)

        if answer.trust_level == "NOT_DETERMINABLE":
            return KPILine(metric_id=metric_id, display_name=spec.semantic_name,
                           trust_level="NOT_DETERMINABLE", presentable=False,
                           reason=answer.not_determinable_reason[:240],
                           conflict_ids=spec.conflict_ids, dq_ids=spec.dq_ids)

        first = answer.results[0] if answer.results else None
        common = dict(
            metric_id=metric_id, display_name=spec.display_name or spec.semantic_name,
            trust_level=answer.trust_level, caveat=answer.caveat,
            conflict_ids=answer.conflict_ids, dq_ids=answer.dq_ids,
            evidence_sources=tuple(first.evidence_sources[:6]) if first else (),
            as_of=first.as_of if first else "",
            validation_status=first.validation_status if first else "",
            confidence=answer.confidence,
            unit=first.unit if first else "",
        )

        # The rule that matters: a headline is shown only where the gate permits one.
        if not answer.headline_permitted:
            return KPILine(
                presentable=False,
                definitions=tuple((r.definition_label, r.value) for r in answer.results),
                reason=(f"{answer.trust_level}: competing definitions exist and no single "
                        f"figure may be stated. "
                        + (f"Conflicts: {', '.join(answer.conflict_ids)}."
                           if answer.conflict_ids else "")),
                **common)

        return KPILine(presentable=True, value=answer.headline, **common)

    # -- sections ----------------------------------------------------------------------------------

    def build(self, include_why=True):
        health = tuple(self.kpi_line(m) for m in BUSINESS_HEALTH_KPIS)
        ops = tuple(self.kpi_line(m) for m in OPERATIONS_KPIS)
        risk_lines = tuple(self.kpi_line(m) for m in RISK_KPIS)

        insights = self.insights.generate()

        # RISKS: the ranked insight set, which already carries severity/trust ordering.
        risks = tuple(
            {"insight_id": i.insight_id, "class": i.insight_class, "trust": i.trust_level,
             "observation": i.observation, "conflict_ids": i.conflict_ids,
             "dq_ids": i.dq_ids, "affected_amount": i.affected_amount,
             "affected_count": i.affected_count}
            for i in insights)

        # ATTENTION REQUIRED: items needing an OWNER decision -- every BLOCK/SHOW_BOTH conflict,
        # because only an owner may settle which definition is authoritative.
        attention = tuple(
            {"insight_id": i.insight_id, "trust": i.trust_level,
             "decision": i.recommendation, "conflict_ids": i.conflict_ids}
            for i in insights
            if i.trust_level in ("BLOCK", "SHOW_BOTH") and i.recommendation.strip())

        changes = self.detector.detect_all(COMPARABLE_MONTHLY_METRICS)
        what_changed = tuple(
            {"metric_id": c.metric_id, "name": c.metric_name,
             "classification": c.classification, "current_period": c.current_period,
             "previous_period": c.previous_period, "absolute_change": c.absolute_change,
             "percentage_change": c.percentage_change, "materiality": c.materiality,
             "reason": c.unavailable_reason, "coverage_note": c.coverage_note}
            for c in changes)

        why = ()
        if include_why:
            why = tuple(
                {"metric_id": a.metric_id, "trust": a.trust_level,
                 "statements": tuple((s.stage, s.text) for s in a.statements),
                 "limitations": a.limitations}
                for a in (self.analyzer.analyze(c.metric_id)
                          for c in changes if c.detected))

        what_to_do = tuple(
            {"insight_id": i.insight_id, "recommendation": i.recommendation,
             "trust": i.trust_level, "confidence": i.confidence,
             "evidence": i.evidence_sources[:4]}
            for i in insights if i.recommendation.strip())

        limitations = [
            ("Materiality is undefined for every change: no threshold exists in the exported "
             "evidence or in any specification (insight_generation_spec.md 2 condition 3)."),
            ("Two of the four documented insight triggers (anomaly, material delta) cannot fire "
             "for the same reason and are reported rather than silently omitted."),
        ]
        blocked = [l.metric_id for l in health + ops if not l.presentable]
        if blocked:
            limitations.append(
                f"{len(blocked)} KPI(s) carry competing definitions and are shown per "
                f"definition rather than as one figure: {', '.join(blocked)}.")

        return ExecutiveSummary(
            business_health=health, operations=ops, risks=risks,
            attention_required=attention, what_changed=what_changed, why=why,
            what_to_do=what_to_do,
            generated_as_of="export snapshot 2026-08-29",
            limitations=tuple(limitations),
        )


def render(summary: ExecutiveSummary):
    """Plain-text briefing. Deterministic and complete on its own -- an LLM may restate it,
    under the same guard every other answer passes through, but never replaces it."""
    out = [f"MANAGEMENT BRIEFING (as at {summary.generated_as_of})", ""]

    out.append(SECTION_BUSINESS_HEALTH)
    for line in summary.business_health:
        out.append(f"  {line.render()}")

    out.append("")
    out.append(SECTION_OPERATIONS)
    for line in summary.operations:
        out.append(f"  {line.render()}")

    out.append("")
    out.append(f"{SECTION_RISKS} ({len(summary.risks)} ranked findings)")
    for r in summary.risks[:12]:
        out.append(f"  [{r['trust']}] {r['insight_id']}: {r['observation'][:150]}")

    out.append("")
    out.append(f"{SECTION_ATTENTION} ({len(summary.attention_required)} owner decisions)")
    for a in summary.attention_required:
        out.append(f"  {a['insight_id']}: {a['decision'][:170]}")

    out.append("")
    out.append(SECTION_WHAT_CHANGED)
    for c in summary.what_changed:
        if c["classification"] == "UNAVAILABLE":
            out.append(f"  {c['name']}: comparison unavailable -- {c['reason'][:130]}")
        else:
            out.append(f"  {c['name']}: {c['classification']} "
                       f"{c['absolute_change']} ({c['percentage_change']}%) "
                       f"{c['previous_period']} -> {c['current_period']}")
            out.append(f"      materiality: undefined (no threshold exists in the evidence)")

    out.append("")
    out.append(SECTION_WHY)
    for w in summary.why:
        out.append(f"  {w['metric_id']}:")
        for stage, text in w["statements"]:
            out.append(f"      {stage}: {text[:160]}")

    out.append("")
    out.append(SECTION_WHAT_TO_DO)
    for a in summary.what_to_do[:12]:
        out.append(f"  [{a['trust']}] {a['recommendation'][:170]}")

    out.append("")
    out.append("LIMITATIONS")
    for l in summary.limitations:
        out.append(f"  - {l}")
    return "\n".join(out)
