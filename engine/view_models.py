"""
view_models.py -- Phase 8. The structured payloads a frontend renders.

Phase 8 brief 19 fixes this module's reason for existing:

    "The frontend must NEVER: calculate business metrics itself · query raw CSV/database
     directly · override trust · select conflict definitions · invent missing values · infer
     unsupported causality · bypass validation · call an LLM for numerical calculation."

Every one of those is prevented structurally rather than by convention: a view model carries
*rendered* values and a *render directive*, and carries no query, no formula, and no raw source
handle. A frontend given one of these has nothing to calculate with.

The load-bearing field on every tile is `headline_permitted`. A BI surface's native idiom is one
number per tile, and three of this business's most important measures cannot honestly be shown
that way. So the refusal is data, not documentation:

    headline_permitted = False  ->  the tile MUST render `definitions[]`, never a single value

`validate_view_model()` catches a payload that violates it, so the failure surfaces in CI rather
than as an owner reading a wrong number.
"""
import re
from dataclasses import dataclass, field

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.execution import MetricExecutor
from engine.bi_contract import BIContractBuilder
from engine.insight_engine import InsightEngine
from engine.change_detection import (ChangeDetector, COMPARABLE_MONTHLY_METRICS,
                                     MATERIALITY_UNDEFINED)
from engine.root_cause import RootCauseAnalyzer
from engine.executive_summary import (ExecutiveSummaryBuilder, BUSINESS_HEALTH_KPIS,
                                      OPERATIONS_KPIS, RISK_KPIS)
from engine.citation import chain_for
from engine import analyst_roles, trust_presentation as tp
from engine import owner_presentation as op
from engine import owner_semantics as osem
from engine import role_scope
from engine import capability_disclosure as cd
from engine import change_detection as cd_detect
from engine import variance
from engine.calculators import rent as rent_calc
from engine.capability_disclosure import CapabilityDisclosure
from engine.result import NOT_DETERMINABLE_TEXT

# Widget vocabulary. A widget is chosen by trust level, never by the author of a screen.
WIDGET_KPI = "kpi_card"
WIDGET_KPI_CAVEAT = "kpi_card_with_caveat"
WIDGET_MULTI_DEF = "multi_definition_panel"
WIDGET_CONFLICT = "conflict_panel_no_headline"
WIDGET_UNAVAILABLE = "not_determinable_notice"

WIDGET_BY_TRUST = {
    "SAFE": WIDGET_KPI,
    "DISCLOSE": WIDGET_KPI_CAVEAT,
    "SHOW_BOTH": WIDGET_MULTI_DEF,
    "BLOCK": WIDGET_CONFLICT,
    "NOT_DETERMINABLE": WIDGET_UNAVAILABLE,
}

# Chart types a metric may support. A metric with no monthly series supports none, and offering
# a chart anyway would mean plotting something the evidence does not contain.
CHART_NONE = "none"
CHART_LINE = "line"
CHART_BAR = "bar"
CHART_MULTI_DEF_BAR = "multi_definition_bar"


@dataclass
class MetricTile:
    """One dashboard tile. Rendered values only -- no formula, no query."""
    metric_id: str
    title: str
    section: str = ""
    widget: str = WIDGET_KPI
    headline_permitted: bool = False
    value: object = None                 # populated ONLY when headline_permitted
    display_value: str = ""              # pre-formatted; the frontend does not compute it
    unit: str = ""
    definitions: tuple = ()              # (label, value, display_value) when no headline
    trust: dict = field(default_factory=dict)     # trust_presentation payload
    caveat: str = ""
    conflict_ids: tuple = ()
    dq_ids: tuple = ()
    evidence: tuple = ()
    validation_status: str = ""
    confidence: str = ""
    as_of: str = ""
    chart_type: str = CHART_NONE
    drilldown_dimensions: tuple = ()
    ai_entry_points: tuple = ()
    unavailable_reason: str = ""
    # One formatted string per point of a month-keyed series, for a chart that must print the
    # engine's figure rather than format one of its own.
    series_display: dict = field(default_factory=dict)
    # The owner-safe half of the measure's semantic contract, carried on the tile.
    #
    # `title` is the registry's display name and reads like one -- "Tenant dues -- Def A:
    # v_outstanding_receivables (reversals excluded)". The frontend used to turn that into a
    # business name itself, which made it a SECOND authority on what a measure is called: the same
    # rules written twice, in two languages, free to drift. `business_name` is the engine's own
    # answer, and the frontend now renders it.
    business_name: str = ""
    business_question: str = ""
    usable_for_decisions: bool = False
    comparable_over_time: bool = False
    # The posture line shown above a measure's competing definitions, said for the number this
    # measure actually holds. Empty where the posture's standing sentence already fits.
    posture_line: str = ""
    # The calculator's own figure, where what an owner is shown is a different but equally real
    # count of the same thing. Only a posture census populates it today: the registry's recorded
    # postures, kept beside the gate's effective ones rather than discarded.
    recorded_value: object = None
    # A composite figure's parts, each named for an owner and formatted by the engine. Built from
    # the value dictionary while its structure is still available, so no surface has to parse the
    # formatted string back apart -- or print "deposit_collections" because it could not.
    display_parts: tuple = ()
    # The caveat as an owner reads it. The registry's `caveat_text` is written for the people who
    # maintain the semantic layer and opens with the posture in machine form; this is the same
    # limitation without that vocabulary. The raw column stays on `caveat` for the technical view.
    owner_caveat: str = ""
    # The competing definitions, labelled for an owner and with composite values named part by
    # part. The raw `definitions` tuple stays beside it for the technical view.
    owner_definitions: tuple = ()
    # The engine's "nothing can be stated" sentence, said without the machine's vocabulary. The
    # raw `unavailable_reason` stays beside it: it names the posture in machine form, which the
    # badge already says in the owner's words.
    owner_unavailable: str = ""

    def as_dict(self):
        return {
            "metric_id": self.metric_id, "title": self.title, "section": self.section,
            "business_name": self.business_name,
            "posture_line": self.posture_line,
            "recorded_value": self.recorded_value,
            "display_parts": [dict(p) for p in self.display_parts],
            "owner_caveat": self.owner_caveat,
            "owner_definitions": [dict(d) for d in self.owner_definitions],
            "owner_unavailable": self.owner_unavailable,
            "business_question": self.business_question,
            "usable_for_decisions": self.usable_for_decisions,
            "comparable_over_time": self.comparable_over_time,
            "widget": self.widget, "headline_permitted": self.headline_permitted,
            "value": self.value, "display_value": self.display_value, "unit": self.unit,
            "series_display": dict(self.series_display),
            "definitions": [{"label": l, "value": v, "display_value": d}
                            for l, v, d in self.definitions],
            "trust": self.trust, "caveat": self.caveat,
            "conflict_ids": list(self.conflict_ids), "dq_ids": list(self.dq_ids),
            "evidence": list(self.evidence), "validation_status": self.validation_status,
            "confidence": self.confidence, "as_of": self.as_of,
            "chart_type": self.chart_type,
            "drilldown_dimensions": list(self.drilldown_dimensions),
            "ai_entry_points": list(self.ai_entry_points),
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass
class InsightCard:
    insight_id: str
    category: str
    category_label: str
    what_happened: str          # OBSERVATION
    why_it_matters: str         # INFERENCE
    evidence: tuple = ()
    confidence: str = ""
    recommended_action: str = ""
    risk: str = ""
    what_would_change_it: str = ""
    trust: dict = field(default_factory=dict)
    conflict_ids: tuple = ()
    dq_ids: tuple = ()
    metric_ids: tuple = ()
    affected_amount: object = None
    affected_count: object = None
    ai_entry_points: tuple = ()
    # Whether the records ESTABLISH this finding or only SHOW the pattern behind it. A recording
    # difference proven against the ledger and a repetition that may be ordinary billing are
    # different claims, and an exceptions view that mixed them would lend the second the
    # certainty of the first.
    evidence_status: str = "established"
    # What this item ASKS OF THE OWNER, from engine/owner_semantics.py. `category` above is the
    # feed's topical grouping (critical, positive, data quality); this is the different and more
    # useful question of whether anyone has to do anything, and who. A surface groups by this to
    # separate what needs attention from what merely happened.
    action_category: str = osem.INFORMATIONAL
    action_category_label: str = ""
    needs_attention: bool = False
    # Where the item came from a data-quality finding, that finding's kind -- so Owner Home and
    # the Data Quality page describe the same finding with the same words.
    action_kind: str = ""
    # For an item that asks something of the owner: what is happening, why it is flagged, what to
    # do, the decision needed (empty where none is), and how the figures are treated until then.
    # `what_happened`, `why_it_matters` and `recommended_action` carry the same text for surfaces
    # that read only those fields.
    guidance: dict = field(default_factory=dict)

    def as_dict(self):
        return {k: (list(v) if isinstance(v, tuple) else v)
                for k, v in self.__dict__.items()}


@dataclass
class ChangeCard:
    metric_id: str
    title: str
    direction: str              # INCREASE / DECREASE / NO_CHANGE / UNAVAILABLE
    display_change: str = ""
    current_period: str = ""
    previous_period: str = ""
    materiality_note: str = ""
    coverage_note: str = ""
    unavailable_reason: str = ""
    trust: dict = field(default_factory=dict)
    ai_entry_points: tuple = ()
    # A requested pair that includes a month the export only partly covers. The figure to date
    # is shown as a figure to date, and the nearest whole-month comparison is offered BESIDE it
    # under its own label -- never in its place.
    partial_note: str = ""
    alternative_note: str = ""
    # The parts of the movement, when the same rows split into named parts that add back up to
    # it exactly. Empty whenever they do not, with `component_note` saying so.
    components: tuple = ()
    component_note: str = ""
    component_basis: str = ""
    # The two figures being compared and the movement between them, each formatted here so the
    # renderer prints a finished string rather than deriving one.
    current_display: str = ""
    previous_display: str = ""
    absolute_display: str = ""
    percent_display: str = ""
    # A movement is a fact about the business, never a task. It carries an action category so a
    # surface can say so structurally rather than by knowing which list it came from.
    action_category: str = ""
    action_category_label: str = ""
    needs_attention: bool = False


@dataclass
class OwnerHome:
    business_health: tuple = ()
    operations: tuple = ()
    risks: tuple = ()
    # The undivided feed, kept as it was so nothing reading it breaks.
    insights: tuple = ()
    changes: tuple = ()
    # The same feed, routed by each item's action category through one table in
    # `engine/owner_semantics.py`: `needs_attention` holds only what someone must act on,
    # `movements` what the business did, `findings` what is worth knowing and asks nothing, and
    # `supporting` the rest. Every card is in exactly one of the four.
    needs_attention: tuple = ()
    movements: tuple = ()
    findings: tuple = ()
    supporting: tuple = ()
    # `needs_attention` grouped into one entry per business subject -- what the page shows, and
    # therefore what its headline counts. The individual findings stay in `needs_attention`.
    attention_subjects: tuple = ()
    action_summary: tuple = ()
    decision_queue: tuple = ()
    recommended_actions: tuple = ()
    trust_summary: dict = field(default_factory=dict)
    as_of: str = ""
    limitations: tuple = ()
    ai_entry_points: tuple = ()

    def all_tiles(self):
        return self.business_health + self.operations + self.risks


# --- formatting ------------------------------------------------------------------------------
# Formatting lives here, not in the frontend: a UI that formats numbers is a UI that can
# round, truncate, or unit-convert a figure away from what the engine computed.

_MONTH = re.compile(r"^\d{4}-\d{2}$")


# The gate's handling of a finding, said to an owner. The value itself is unchanged and is still
# carried on the record; this is only how it reads on the page.
_DQ_POSTURE_LABELS = {
    "BLOCK": "Decision / correction required",
    "SHOW_BOTH": "Definitions need review",
    "DISCLOSE": "Management should be aware",
    "SAFE": "Monitor / no immediate action",
    "NOT_DETERMINABLE": "Cannot be determined from the exported records",
}

# What an owner is being asked to DO about a finding, and what KIND of thing a finding is, are
# decided in engine/owner_semantics.py -- beside the gate rather than beside a renderer, so that
# the Data Quality page, Owner Home, the workspaces, the AI answers and decision support all
# project the same decision instead of each making their own. The names below are the call sites
# this module already had; the decisions behind them are no longer made here.
_dq_action_kind = osem.dq_action_kind
_names_an_object = osem.names_an_object
_speaks_machine = osem.speaks_machine


def _dq_business_area(row):
    """The finding's business area, keeping only the parts that name a business, not a table.

    The register writes an area as one or more "/"-separated parts, and some of them name the
    plumbing rather than the business -- "Ledger function correctness", "Data quality / schema".
    Those parts are dropped and the business ones kept, so what is left is the part of the
    business an owner recognises. An area with no business part at all returns empty, and the
    caller names the affected measures instead.
    """
    area = op.sanitize_owner_text(str(row.get("business_area", "") or ""))
    parts = [p.strip() for p in area.split("/")
             if p.strip() and not _names_an_object(p) and not _speaks_machine(p)]
    return " / ".join(parts)


def _dq_owner_issue(row, kind, measure_names=()):
    """The finding's own sentence where it survives being said without database object names,
    and a composed one where it does not.

    A finding written around an object name loses its subject when the name is removed --
    "(v1) totalProfit omits owner rent", "buckets are CURRENT_DATE-dependent" -- and patching
    the fragment back into a sentence produces worse English than the name would have been.
    This project has been here before: the fix is to compose from the fields, not to operate on
    the prose. So a damaged sentence is replaced by a plain statement built from the record's
    own business area and the kind of thing the finding is, and the original wording is kept and
    shown under the technical details, where the object names belong.

    Saying only "a recording or definition problem" was accurate about every finding and useful
    about none: an owner reading it could not tell a date that will not parse from a check that
    was never written. The kind is already established for the action; the same word makes this
    sentence say something.
    """
    original = str(row.get("issue", "") or "")
    cleaned = op.sanitize_owner_text(original)
    if (cleaned == original and not _names_an_object(cleaned)
            and not _speaks_machine(cleaned)):
        return cleaned
    # The business area first, because it says WHERE in the business this is. Where the register
    # gives no business area at all -- "Ledger function correctness" is entirely plumbing -- the
    # measures the finding touches say the same thing, and they are the owner's own words for
    # them.
    subject = _dq_business_area(row)
    if not subject and measure_names:
        subject = (", ".join(measure_names[:-1]) + " and " + measure_names[-1]
                   if len(measure_names) > 1 else measure_names[0])
    return osem.dq_owner_lead(kind, subject)


def _dq_why(measure_names, affected_amount, posture):
    """Why the finding matters, from the measures it touches and the gate's own handling.

    The amount is quoted exactly as the record states it -- including the phrase used when no
    amount can be established, which must not become a zero or disappear.
    """
    if measure_names:
        listed = (", ".join(measure_names[:-1]) + " and " + measure_names[-1]
                  if len(measure_names) > 1 else measure_names[0])
        lead = (f"Figures for {listed} are read from the records this affects, so they carry it "
                f"too.")
    else:
        lead = ("No measure on the dashboard depends on this, so it changes no figure you are "
                "shown. It is recorded because the records show it.")
    amount = str(affected_amount or "").strip()
    if amount and NOT_DETERMINABLE_TEXT.rstrip(".").lower() in amount.lower():
        lead += " The size of what is affected is not determinable from exported evidence."
    elif (amount and op.sanitize_owner_text(amount) == amount
            and not _names_an_object(amount) and not _speaks_machine(amount)
            # "N/A", and equally "N/A (formatting defect, not an amount discrepancy)": the record
            # is saying there is no amount, in a note written for the register. Printing it after
            # "What it covers:" turns a stated absence into a quantity.
            and not amount.upper().startswith("N/A")):
        # Quoted exactly as the record states it, and only when it states it without naming a
        # database object -- an amount whose sentence would be damaged by removing one stays in
        # the technical details, whole, instead of being shown in pieces.
        lead += f" What it covers: {amount}"
        if not lead.rstrip().endswith("."):
            lead += "."
    # The posture clause speaks about the affected measures, so it is only said where there are
    # some: "no single figure can be stated for them" has nothing to refer to otherwise.
    if measure_names and posture == "BLOCK":
        lead += " No single figure can be stated for them until it is settled."
    elif measure_names and posture == "SHOW_BOTH":
        lead += " Every competing definition is shown rather than one being chosen."
    return lead


def _answers_a_scoped_question(tile):
    """Whether a tile actually carries an answer, as opposed to a reason it has none.

    Used only when a narrowing filter is active. A measure that produced a figure, a set of
    competing definitions, or a formatted value has answered; one that produced only an
    unavailable_reason has not, and under a filter it is dropped rather than displayed. The test
    is on what the tile HOLDS, never on why -- so it needs no list of which measures support
    which dimension, and it cannot fall out of step with the calculators.
    """
    return bool(tile.get("display_value")
                or tile.get("value") is not None
                or tile.get("definitions"))


def _clean_filters(filters):
    """The analyst's selection, in the shapes the engine already speaks.

    A month is accepted only in the form the series is keyed by; anything else is dropped here
    rather than reaching the detector as a period that matches nothing. An apartment code is
    upper-cased and passed on WITHOUT being checked against the export -- the rent calculator's
    own resolver rejects an unknown one, in its own words, and second-guessing it here would put
    a second definition of "known apartment" in the system.
    """
    raw = filters or {}
    out = {"period": "", "compare": "", "apartment": ""}
    for key in ("period", "compare"):
        value = str(raw.get(key) or "").strip()
        if _MONTH.match(value):
            out[key] = value
    apartment = str(raw.get("apartment") or "").strip().upper()
    out["apartment"] = apartment
    return out


# The owner's status for a SAFE measure whose calculation was checked against the source view but
# whose source records carry a proven completeness finding.
SOURCE_LIMITATION_STATUS = "Calculation verified \u00b7 Source-data limitation"


def format_value(value, unit=""):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        # The currency test is on whole words. As a substring, "RS" also matches the "pairs"
        # in "bed x allotment pairs", which printed a count of overlapping allotments as a
        # rupee amount.
        u = (unit or "").upper()
        if re.search(r"\b(?:INR|RS)\b", u) or "₹" in unit:
            return f"₹{value:,.2f}"
        if isinstance(value, float) and not float(value).is_integer():
            return f"{value:,.2f}"
        return f"{value:,.0f}"
    if isinstance(value, dict):
        # A breakdown keyed by the gate's own posture names -- the trust overview counts measures
        # per level -- reads to an owner as "SAFE: 18; DISCLOSE: 24". The key is relabelled with
        # the ONE owner phrase for that posture, from the same table every badge uses. Generic:
        # any key that IS a canonical level is relabelled, and no other key is touched. The
        # counts, the ordering and the levels themselves are unchanged.
        return "; ".join(
            f"{osem.OWNER_TRUST_STATUS.get(k, k)}: {format_value(v, unit)}"
            for k, v in list(value.items())[:6])
    return str(value)


class ViewModelBuilder:
    """Builds every Phase 8 view model from engine output. Computes nothing of its own."""

    def __init__(self, registry: SemanticRegistry = None, gate: TrustGate = None,
                 executor: MetricExecutor = None):
        self.registry = registry or SemanticRegistry()
        self.gate = gate or TrustGate(self.registry)
        self.executor = executor or MetricExecutor(registry=self.registry, gate=self.gate)
        self.bi = BIContractBuilder(self.registry, self.gate, self.executor)
        self.insight_engine = InsightEngine(self.registry, self.gate, self.executor)
        self.detector = ChangeDetector(self.registry, self.gate, self.executor)
        self.analyzer = RootCauseAnalyzer(self.registry, self.gate, self.executor,
                                          self.detector)
        self.summary_builder = ExecutiveSummaryBuilder(
            self.registry, self.gate, self.executor, self.insight_engine,
            self.detector, self.analyzer)
        self._dq_rows = {r.get("dq_id"): r for r in self.insight_engine.dq_rows}
        # What this system can and cannot analyse. Read from the capability
        # registry so an unsupported analysis is DISCLOSED rather than omitted.
        self.capabilities = CapabilityDisclosure()

    # -- tiles -----------------------------------------------------------------------------------

    def _source_completeness_findings(self, dq_ids):
        """Findings, by id, that prove the source records behind a measure are incomplete.

        Read off the data-quality register's own fields: severity HIGH, status MEASURED, a root
        cause recorded as PROVEN, and a business area the register itself describes as a
        completeness problem. Nothing is inferred from the finding's prose.
        """
        out = []
        for dq_id in dq_ids or ():
            row = self._dq_rows.get(dq_id) or {}
            if (str(row.get("severity", "")).upper() == "HIGH"
                    and str(row.get("status", "")).upper() == "MEASURED"
                    and str(row.get("root_cause_confidence", "")).upper().startswith("PROVEN")
                    and "completeness" in str(row.get("business_area", "")).lower()):
                out.append(dq_id)
        return tuple(out)

    def tile(self, metric_id, section="", **calc_kwargs):
        if metric_id not in self.registry:
            pres = tp.present("NOT_DETERMINABLE")
            return MetricTile(
                metric_id=metric_id, title=metric_id, section=section,
                widget=WIDGET_UNAVAILABLE, headline_permitted=False, trust=pres.as_dict(),
                unavailable_reason=f"{metric_id!r} is not a semantic metric. "
                                   f"{NOT_DETERMINABLE_TEXT}")

        spec = self.registry.get(metric_id)
        card = self.bi.card(metric_id, **calc_kwargs)

        # The tile shows the GATE's posture, not the answer's. They differ for a metric whose
        # trust level is settled but whose calculation is not implemented (M.OCC.005): the
        # answer degrades to NOT_DETERMINABLE while the metric remains SHOW_BOTH. Showing the
        # degraded level would tell the owner the conflict does not exist, when the truth is
        # that the conflict exists and its figures cannot yet be computed.
        gate_level = self.gate.authorize(metric_id).effective_level
        answer_degraded = (card.trust_level == "NOT_DETERMINABLE"
                           and gate_level != "NOT_DETERMINABLE")
        effective_level = gate_level
        # The validation result decides whether a SAFE tile may say "checked"; the gate's level
        # is unchanged.
        pres = tp.present(effective_level, validation_status=card.validation_status)
        trust = pres.as_dict()
        # "Verified" alone says the figure is right. Where the calculation was checked but the
        # records it reads are proven incomplete, the owner is told both halves. The SAFE posture
        # itself is unchanged; only the owner's short status says what was verified.
        incomplete = self._source_completeness_findings(card.dq_issues)
        if effective_level == "SAFE" and card.validation_status == "MATCH" and incomplete:
            trust = dict(trust, owner_status=SOURCE_LIMITATION_STATUS,
                         badge=SOURCE_LIMITATION_STATUS, source_data_limitations=incomplete)

        # The owner-safe half of the semantic contract, attached to the tile so no surface has to
        # derive a business name, a business question or a usability answer for itself. The
        # contract reads the same registry row and the same gate decision this tile does, so the
        # two cannot disagree.
        contract = self.metric_contract(metric_id)
        safe = set(contract.get("owner_safe_fields") or ())

        tile = MetricTile(
            metric_id=metric_id,
            title=spec.display_name or spec.semantic_name,
            # `business_name` is always safe by construction -- it is the owner-facing name --
            # but the question is the registry's own description and sometimes names an
            # application object, so it travels only when the contract says it may be shown.
            business_name=contract.get("business_name", ""),
            business_question=(contract.get("business_question", "")
                               if "business_question" in safe else ""),
            usable_for_decisions=bool(contract.get("usable_for_decisions")),
            comparable_over_time=bool(contract.get("comparable_over_time")),
            section=section,
            widget=WIDGET_BY_TRUST[effective_level],
            headline_permitted=card.headline_permitted and not answer_degraded,
            unit=card.unit,
            trust=trust,
            caveat=card.caveat,
            conflict_ids=card.conflicts,
            dq_ids=card.dq_issues,
            evidence=tuple(str(e) for e in card.evidence[:6]),
            validation_status=card.validation_status,
            confidence=card.confidence,
            as_of=card.period,
            drilldown_dimensions=self._drilldown_dimensions(spec),
            ai_entry_points=self._entry_points(metric_id, card.trust_level),
        )

        if effective_level == "NOT_DETERMINABLE":
            tile.unavailable_reason = card.not_determinable_reason or NOT_DETERMINABLE_TEXT
            tile.owner_unavailable = op.sanitize_owner_text(tile.unavailable_reason)
            tile.owner_caveat = self._owner_caveat(tile, pres)
            tile.chart_type = CHART_NONE
            return tile

        if answer_degraded:
            # The conflict is real; its figures are not computable in the current engine. The
            # tile keeps the conflict posture and says why there are no numbers, rather than
            # implying comparable values exist.
            #
            # A NARROWED request degrades for a different reason -- the calculator does not
            # support the filter that was asked for -- and the executor already wrote that
            # sentence. Replacing it with the generic one would tell the owner the conflict is
            # uncomputable when what happened is that this measure cannot be read per apartment.
            #
            # Only a refusal the EXECUTOR wrote for the owner may replace it. A metric with no
            # calculator degrades with a sentence written for the people building this system --
            # it names the semantic layer, the execution engine and a phase report -- and that
            # sentence must not reach an owner just because a filter happened to be set.
            #
            # The generic sentence is about COMPETING DEFINITIONS, so it may only be used where
            # the posture actually means that. A measure the gate marks SAFE or DISCLOSE has no
            # competing definitions: when its answer degrades it is because the calculation was
            # refused -- a filter it cannot honour, or a parameter it needs and was not given --
            # and the executor has already written that sentence for the owner. Telling the
            # owner "competing definitions" there names a conflict that does not exist.
            #
            # The one refusal that may never be shown is the missing-calculator message, which
            # is written for the people building this system.
            narrowed = any(v not in (None, "", (), {}) for v in calc_kwargs.values())
            refusal = card.not_determinable_reason or ""
            developer_wording = "execution engine" in refusal
            multi_definition = effective_level in ("SHOW_BOTH", "BLOCK")
            tile.unavailable_reason = (
                refusal if refusal and not developer_wording
                and (narrowed or not multi_definition)
                else (f"This measure carries competing definitions, but their values are not "
                      f"computable in the current engine, so the conflict is shown without "
                      f"figures. {NOT_DETERMINABLE_TEXT}"))
            tile.owner_unavailable = op.sanitize_owner_text(tile.unavailable_reason)
            tile.owner_caveat = self._owner_caveat(tile, pres)
            tile.chart_type = CHART_NONE
            return tile

        if tile.headline_permitted:
            tile.value, tile.recorded_value, census_note = self._posture_census(card.value)
            tile.display_value = format_value(tile.value, card.unit)
            # The parts, named for an owner, from the dictionary rather than from the string
            # above. Every surface reads these instead of splitting `display_value` itself.
            tile.display_parts = op.owner_value_parts(
                tile.value, lambda v: format_value(v, card.unit))
            if census_note:
                # Rendered WITH the figures, not behind them: the reader is being told which of
                # two real counts they are looking at.
                tile.caveat = (f"{tile.caveat} {census_note}".strip() if tile.caveat
                               else census_note)
            # A breakdown gets one finished string per entry, so a chart tooltip or a bar label
            # prints the engine's figure rather than a second rendering of it made in the
            # browser -- which is how the same rent came to read "19,500" in one place and
            # "19,500.00" a few lines below it.
            if isinstance(tile.value, dict):
                tile.series_display = {
                    k: format_value(v, card.unit) for k, v in tile.value.items()
                    if isinstance(k, str) and isinstance(v, (int, float))
                    and not isinstance(v, bool)}
            tile.chart_type = self._chart_for(metric_id, effective_level)
        else:
            # The refusal, rendered as data. No value field is populated at all -- a frontend
            # cannot accidentally display a headline it was never given.
            tile.definitions = tuple(
                (label, val, format_value(val, card.unit)) for label, val in card.definitions)
            # The same definitions, labelled for an owner and with any composite value named
            # part by part. Every definition is here, in the engine's order, with its own
            # figure: this renames, and renames only.
            owner_labels = op.owner_definition_labels(
                [label for label, _ in card.definitions])
            tile.owner_definitions = tuple(
                {"label": owner_labels[index],
                 "value": format_value(val, card.unit),
                 "parts": [dict(p) for p in op.owner_value_parts(
                     val, lambda v: format_value(v, card.unit))]}
                for index, (_, val) in enumerate(card.definitions))
            # SHOW_BOTH's standing sentence says "review both", which is right for two readings
            # and wrong for occupancy's five. The count is this tile's own, so the line is said
            # for the number it holds rather than by a rule about any particular measure. BLOCK
            # keeps its own sentence, which names no number.
            if effective_level == "SHOW_BOTH" and len(tile.definitions) >= 2:
                tile.posture_line = osem.definitions_line(len(tile.definitions))
            # SHOW_BOTH permits a side-by-side comparison visual. BLOCK does not: a bar chart of
            # the competing values invites the eye to pick the tallest, which is a soft way of
            # choosing the winner the trust policy forbids choosing.
            tile.chart_type = (CHART_MULTI_DEF_BAR
                               if effective_level == "SHOW_BOTH" and len(tile.definitions) >= 2
                               else CHART_NONE)

        tile.owner_caveat = self._owner_caveat(tile, pres)
        tile.owner_unavailable = op.sanitize_owner_text(tile.unavailable_reason or "")
        return tile

    @staticmethod
    def _owner_caveat(tile, pres):
        """The measure's limitation, said without the machine's vocabulary.

        The registry's caveat column is written for the people who maintain the semantic layer:
        it opens with the posture in machine form and cites the conflict and finding records
        behind it -- "SHOW_BOTH: present every definition with its label ... See conflicts.md
        C.001". Correct for the audit trail, and unreadable as an owner's caveat.

        So the recorded sentence is shown only where it survives being read aloud, and where it
        does not, the gate's own owner sentence stands in its place. That sentence is already
        business language and states the same limitation -- it is what the posture MEANS. The
        recorded column is untouched and stays on `caveat` for the technical panel.

        Nothing is softened: a measure with a limitation still carries one, and a caveat is never
        dropped without another sentence taking its place.
        """
        recorded = str(tile.caveat or "").strip()
        # The test is on the ORIGINAL, not on a cleaned copy. Cleaning first and testing after
        # passes a sentence whose subject was the thing removed -- "answer, but state the known
        # limitation", "present every definition with its label ... for the full comparison" --
        # which is the failure this project has already hit twice. A sentence written around the
        # machine's vocabulary is not repaired by deleting the vocabulary; it is replaced.
        if recorded and osem.owner_safe(recorded):
            return op.sanitize_owner_text(recorded)
        if recorded or not pres.headline_permitted:
            return pres.owner_explanation or ""
        return ""

    def gate_trust_distribution(self):
        """How many measures sit at each posture, AFTER the gate has ruled on every one.

        The one canonical answer to "which of my numbers can I trust". Every owner-facing surface
        that shows a posture census reads it from here, because the gate is the authority on what
        a measure's posture actually IS -- not what the registry recorded before propagation.
        """
        counts = {}
        for metric_id in self.registry.all_ids():
            level = self.gate.authorize(metric_id).effective_level
            counts[level] = counts.get(level, 0) + 1
        return counts

    def _propagation_differences(self):
        """The measures whose final posture differs from the one recorded against them.

        A measure inherits the strongest posture of the measures it depends on
        (`metric_dependency_graph.md` 6), so a recorded SHOW_BOTH can end up BLOCK. This is the
        gate working, not a discrepancy -- but two censuses of "the same thing" that differ by one
        and explain nothing IS a discrepancy to whoever reads them.
        """
        return tuple(
            m for m in self.registry.all_ids()
            if self.gate.authorize(m).effective_level != self.registry.get(m).trust_level)

    def _posture_census(self, value):
        """A measure whose value is a count of measures per posture is a posture census.

        Two of them exist and they are both correct. The registry's `ai_trust_status` column
        records what each measure was ASSIGNED; the gate reports what each measure's posture
        EFFECTIVELY IS once dependency propagation has run. They differ wherever a measure
        inherits a stronger posture than the one written against it.

        The owner-facing figure must be the gate's, because the gate is what actually decides
        whether a figure may be stated -- an overview that reported the recorded column would
        tell an owner a measure is merely conflicted when the system will in fact refuse to state
        a number for it. The recorded census is not lost: it stays on the tile, and the tile says
        in its caveat that the two differ and by how much.

        Detected by SHAPE -- every key is a canonical posture -- so this names no metric and no
        identifier. Nothing is recomputed in a view: both censuses are counted by the engine.
        """
        levels = set(osem.OWNER_TRUST_STATUS)
        if not (isinstance(value, dict) and value and set(value) <= levels):
            return value, None, ""

        gate_counts = self.gate_trust_distribution()
        if dict(value) == gate_counts:
            return value, None, ""

        differing = self._propagation_differences()
        note = (
            f"These are the postures the trust gate reaches for each measure. "
            f"{len(differing)} of them ended up stronger than the posture first recorded against "
            f"the measure, because a measure inherits the strongest posture of the measures it "
            f"depends on. The originally recorded counts are in the technical details.")
        return gate_counts, dict(value), note

    @staticmethod
    def _has_time_series(spec):
        """Does this metric have a historical form at all? A snapshot-only measure ("not a time
        series", "a live worklist", "current-state") cannot answer a change question."""
        policy = (spec.historical_policy or "").lower()
        date_field = (spec.date_field or "").lower()
        snapshot_markers = ("not a time series", "current-state", "current-value",
                            "live worklist", "not a time-series", "single value, not a range")
        if any(m in policy or m in date_field for m in snapshot_markers):
            return False
        if "not applicable" in date_field and "not applicable" in policy:
            return False
        return True

    def _chart_for(self, metric_id, trust_level):
        """A chart is offered only where a series actually exists. Offering one otherwise means
        plotting something the evidence does not contain."""
        if trust_level in ("SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE"):
            return CHART_NONE
        if metric_id in COMPARABLE_MONTHLY_METRICS:
            return CHART_LINE
        spec = self.registry.get(metric_id)
        if "month" in (spec.dimensions or "").lower():
            return CHART_LINE
        return CHART_NONE

    def _drilldown_dimensions(self, spec):
        from engine.dimension_resolver import KNOWN_DIMENSIONS, DEGENERATE_DIMENSIONS
        out = []
        d = (spec.dimensions or "").lower()
        for dim in sorted(KNOWN_DIMENSIONS):
            if dim in DEGENERATE_DIMENSIONS:
                continue          # 1 distinct value -- a drilldown would be a single row
            if dim.replace("_id", "") in d or dim in d:
                out.append(dim)
        return tuple(out)

    def _entry_points(self, metric_id, trust_level):
        """Phase 8 brief 5: View → Ask Why → Drill Down → Explain → Recommend.

        An entry point is offered only where the engine can actually answer it. Offering "Why?"
        on a snapshot-only measure invites a question the engine must refuse -- M.RISK.003 is a
        live worklist with no time series, so "why did it change?" presupposes a change that
        cannot be established. A button that always fails is worse than an absent one.
        """
        spec = self.registry.get(metric_id)
        eps = [
            {"action": "explain", "label": "How was this calculated?",
             "question": f"How was {metric_id} calculated?", "metric_id": metric_id},
        ]
        if self._has_time_series(spec):
            eps.append({"action": "why", "label": "Why?",
                        "question": f"Why did {spec.semantic_name} change?",
                        "metric_id": metric_id})
        eps.append({"action": "trust", "label": "Can I trust this?",
                    "question": "Which numbers should I trust?", "metric_id": metric_id})
        if trust_level in ("SHOW_BOTH", "BLOCK"):
            eps.insert(0, {"action": "conflict", "label": "View all definitions",
                           "question": "Which definition should we use?",
                           "metric_id": metric_id})
        return tuple(eps)

    # -- owner home -------------------------------------------------------------------------------

    def owner_home(self):
        summary = self.summary_builder.build()

        health = tuple(self.tile(m, "Business Health") for m in BUSINESS_HEALTH_KPIS)
        ops = tuple(self.tile(m, "Operations") for m in OPERATIONS_KPIS)
        risks = tuple(self.tile(m, "Risks") for m in RISK_KPIS)

        raw_changes = self.detector.detect_all(COMPARABLE_MONTHLY_METRICS)
        changes = tuple(self._change_card(c) for c in raw_changes)

        # The insight feed carries BOTH standing findings and validated period changes. Without
        # the changes, the Positive category is permanently empty -- not because nothing moved,
        # but because movements were only ever rendered in a separate strip the owner might not
        # connect to the risk feed.
        # The figures the owner guidance quotes: calculator outputs and register fields, gathered
        # once for this page. Nothing is computed for the guidance itself.
        facts = self._guidance_facts()
        insights = (tuple(self._insight_card(i, facts) for i in self.insight_engine.generate())
                    + tuple(c for c in (self._change_insight(ch) for ch in raw_changes)
                            if c is not None))

        # Findings the owner should KNOW about but need do nothing about.
        #
        # The proactive insight engine admits a finding only at CRITICAL or HIGH severity, which
        # `insight_generation_spec.md` 2 condition 1 fixes and this pass does not touch. But
        # severity answers "how bad", not "does anyone need to see this" -- so under that rule
        # alone every monitor-class finding was invisible to the owner and the block meant for
        # them was permanently empty, while the register listed them all along.
        #
        # So the visibility rule here is the ACTION CATEGORY, not the severity: a finding the
        # deterministic classifier calls MONITOR is projected onto the feed as itself. It cannot
        # raise the attention count, because MONITOR routes to the monitor block by the same
        # table every other item is routed by.
        already = {d for card in insights for d in (card.dq_ids or ())}
        monitor = tuple(self._dq_monitor_card(row) for row in self.insight_engine.dq_rows
                        if row.get("dq_id") and row["dq_id"] not in already
                        and osem.dq_action_category(osem.dq_action_kind(row)) == osem.MONITOR)
        insights = insights + monitor

        # The queue and the action list restate an insight's recommendation, and the engine's
        # own wording names the record it came from. Stripping that identifier out mid-sentence
        # left "Recommend an owner decision resolving the definitional conflict behind before
        # any figure it affects is used" -- eight times over, each dangling on the same word.
        # The owner-facing sentence composed for the insight card is reused instead, so the
        # subject is resolved once and every surface says the same thing.
        owner_actions = {card.insight_id: card.recommended_action
                         for card in insights if card.recommended_action}
        guidance_by_insight = {card.insight_id: card.guidance
                               for card in insights if card.guidance}

        def _owner_action(insight_id, fallback):
            return owner_actions.get(insight_id) or op.sanitize_owner_text(fallback) or (
                "Review this finding before the figures it affects are used for a decision.")

        # One row per insight record produced eleven cards for five decisions, four of them
        # saying the same thing about receivables. The queue is grouped by the business subject
        # each row is about, which is what the owner is deciding on. Nothing is dropped and no
        # definition conflict is merged into a recording problem: they ask for different things.
        subjects_by_insight = {card.insight_id: op.owner_subject_names(card.metric_ids,
                                                                       self.registry)
                               for card in insights}
        # Which measures each queued item is actually about. Owner Home does not use it -- it
        # shows the whole queue -- but a role workspace does, to leave out a decision about
        # measures its lens cannot see.
        metrics_by_insight = {card.insight_id: tuple(card.metric_ids or ())
                              for card in insights}
        grouped = op.group_owner_decisions(
            [{"insight_id": a["insight_id"], "trust": a["trust"],
              "decision": _owner_action(a["insight_id"], a["decision"]),
              "conflict_ids": list(a["conflict_ids"]),
              "metric_ids": metrics_by_insight.get(a["insight_id"], ()),
              "guidance": guidance_by_insight.get(a["insight_id"], {})}
             for a in summary.attention_required],
            subjects_by_insight)
        decision_queue = tuple(
            {**row,
             # The canonical owner phrase for the posture, not the long standing sentence. That
             # sentence says "review both", which a queue row has no definition count to check
             # and which is wrong above two readings -- and it was a third wording of a posture
             # the badge beside it already states.
             "owner_facing": (tp.present(row["trust"]).owner_status
                              if row["trust"] and row.get("kind") == "decision" else "")}
            for row in grouped)

        actions = tuple(
            {"insight_id": a["insight_id"],
             "recommendation": _owner_action(a["insight_id"], a["recommendation"]),
             "trust": a["trust"],
             "confidence": op.owner_confidence(a["confidence"]),
             "evidence": list(a["evidence"]),
             "guidance": guidance_by_insight.get(a["insight_id"], {})}
            for a in summary.what_to_do)

        # The same canonical census the trust-overview measure now presents, so the two cannot
        # differ: one method, counted once, read by both.
        trust_summary = {lv: {"count": n, **tp.present(lv).as_dict()}
                         for lv, n in self.gate_trust_distribution().items()}

        # The feed, split by what each item ASKS OF THE OWNER rather than by what it is about.
        #
        # This is the split that was missing. One feed held standing findings and validated period
        # movements together, and every surface reading it counted the lot as "attention" -- so a
        # month in which revenue rose reported one more thing needing attention than a month in
        # which nothing happened. A movement is a fact about the business; it belongs beside the
        # other facts, not on the work list.
        #
        # Nothing is dropped and nothing is duplicated: every card lands in exactly one of the
        # three, decided by its own action category, and `insights` still carries all of them for
        # anything reading the undivided feed.
        # What needs attention, counted the way it is READ: one entry per business subject.
        #
        # Three findings about tenant dues are three findings, and they are all still here -- but
        # an owner scanning the page sees ONE thing to deal with, not three, and a headline of
        # twenty over a list of fifteen subjects describes neither. So the feed is grouped by the
        # subject each item is about, using the same subject the decision queue groups by, and
        # the headline counts subjects. The breakdown beside it says what those subjects ask for.
        #
        # Nothing is dropped: a group carries its members, and every individual finding remains
        # in `needs_attention`, on the Data Quality page, and on the metric and conflict surfaces.
        grouped_feed = {g: [] for g in osem.HOME_GROUPS}
        for card in insights:
            grouped_feed[osem.home_group(card.action_category)].append(card)
        needs_attention = tuple(grouped_feed[osem.GROUP_ATTENTION])
        movements = tuple(grouped_feed[osem.GROUP_MOVEMENTS])
        findings = tuple(grouped_feed[osem.GROUP_MONITOR])
        supporting = tuple(grouped_feed[osem.GROUP_SUPPORTING])
        attention_subjects = self._attention_subjects(needs_attention)

        return OwnerHome(
            business_health=health, operations=ops, risks=risks,
            insights=insights, changes=changes,
            needs_attention=needs_attention, movements=movements, findings=findings,
            supporting=supporting, attention_subjects=attention_subjects,
            action_summary=tuple(
                {"category": c,
                 "label": osem.ACTION_CATEGORIES[c]["label"],
                 "meaning": osem.ACTION_CATEGORIES[c]["owner_meaning"],
                 "needs_attention": osem.needs_attention(c),
                 "count": sum(1 for card in insights if card.action_category == c)}
                for c in sorted(osem.ALL_ACTION_CATEGORIES, key=osem.category_order)
                if any(card.action_category == c for card in insights)),
            decision_queue=decision_queue, recommended_actions=actions,
            trust_summary=trust_summary,
            as_of=op.owner_as_of(summary.generated_as_of),
            # The summary's limitations are written for the audit trail and name the
            # specification clause and the metric records behind each one.
            limitations=(tuple(op.owner_limitation(l) for l in summary.limitations)
                         + (op.CLASSIFICATION_CAVEAT,)),
            ai_entry_points=(
                {"action": "briefing", "label": "How is my business doing?",
                 "question": "How is the business doing?"},
                {"action": "changed", "label": "What changed?",
                 "question": "What changed this month?"},
                {"action": "focus", "label": "What should I focus on today?",
                 "question": "What should I do?"},
                {"action": "risks", "label": "What are my biggest risks?",
                 "question": "What are our biggest business risks?"},
                {"action": "trust", "label": "Which numbers can I trust?",
                 "question": "Which numbers should I trust?"},
            ),
        )

    def _guidance_facts(self):
        """The figures the owner guidance quotes, read from the engine's own outputs and the
        data-quality register. Nothing is computed here: every value is a calculator output or a
        recorded register field. A figure that cannot be read is left out, and the guidance that
        needed it falls back to the item's existing wording."""
        facts = {"dq": dict(self._dq_rows)}

        def answer(metric_id):
            try:
                return self.executor.execute(metric_id)
            except Exception:
                return None

        def definitions(result):
            if result is None or not result.results:
                return []
            labels = [r.definition_label for r in result.results]
            owner = op.owner_definition_labels(labels) if len(labels) > 1 else labels
            return [(label, r.value) for label, r in zip(owner, result.results)]

        def first(result):
            return result.results[0] if result is not None and result.results else None

        occupancy = answer("M.OCC.001")
        facts["occupancy"] = definitions(occupancy)
        facts["historical"] = [label for label, _ in definitions(answer("M.OCC.005"))]
        facts["staying"] = getattr(first(answer("M.TEN.001")), "value", None)
        facts["on_notice"] = getattr(first(answer("M.TEN.002")), "value", None)
        facts["tenant_dues"] = definitions(answer("M.AR.001A"))
        facts["owner_rent"] = definitions(answer("M.OWN.002"))
        profit = answer("M.PROFIT.001")
        facts["profit"] = definitions(profit)
        gaps = [d.get("absolute_difference")
                for d in ((profit.numeric_difference or {}).values() if profit else ())]
        facts["profit_gap"] = max((g for g in gaps if isinstance(g, (int, float))), default=None)
        facts["repeated_invoices"] = getattr(first(answer("M.RISK.005")), "value", None)
        facts["phantom_deposits"] = getattr(first(answer("M.RISK.004")), "value", None)
        receipts = first(answer("M.RISK.006"))
        facts["duplicate_receipts"] = getattr(receipts, "value", None)
        facts["duplicate_receipts_note"] = getattr(receipts, "limitations", "") or ""
        facts["overlaps"] = getattr(first(answer("M.RISK.007")), "value", None)
        reconciliation = getattr(first(answer("M.RISK.008")), "value", None) or {}
        facts["settlement_recon"] = reconciliation.get("deposit_settlements")
        facts["settlement_totals"] = getattr(first(answer("M.DEP.002")), "value", None)
        categories = getattr(first(answer("M.EXP.002")), "value", None) or {}
        facts["electricity"] = categories.get("electricity")
        facts["expenses_total"] = getattr(first(answer("M.EXP.001")), "value", None)
        return facts

    def _insight_card(self, insight, facts=None):
        dq_sev = ""
        dq_kind = ""
        # The findings behind this insight, classified by the same classifier the Data Quality
        # page uses -- so an insight raised BY a finding inherits what that finding asks for, and
        # the two pages cannot describe the same problem as needing different things.
        #
        # An insight can carry several findings, and taking the FIRST one meant an arbitrary
        # choice decided what the owner was asked to do. The strongest ask wins instead: grouping
        # several findings under one card may not soften what any of them needs.
        kinds = []
        for d in insight.dq_ids:
            row = self._dq_rows.get(d)
            if row:
                if not dq_sev:
                    dq_sev = row.get("severity", "")
                kinds.append(osem.dq_action_kind(row))
        if kinds:
            strongest = osem.most_demanding([osem.dq_action_category(k) for k in kinds])
            dq_kind = next(k for k in kinds if osem.dq_action_category(k) == strongest)
        cat = tp.categorise_insight(insight, dq_sev)
        action_category = osem.insight_action_category(
            insight.trigger, insight.trust_level, dq_kind)
        # The owner-facing four. Composed from the insight's structured fields rather than from
        # the engine's own prose, which names records, specification clauses and internal
        # statuses -- correct for the audit trail, and unreadable on the Owner Home. The
        # originals stay on the insight object for the evidence chain.
        subjects = op.owner_subject_names(insight.trigger_metric_ids, self.registry)
        what, why, action, changes_it = op.owner_insight_view(insight, cat, subjects)
        # An item that asks something of the owner is said in the five-part guidance structure,
        # built from the evidence behind it. Its trust posture and category are unchanged.
        guidance = {}
        if osem.needs_attention(action_category):
            guidance = op.owner_guidance(insight.insight_id, facts or {}, insight.trust_level,
                                         op.owner_subject_of(subjects), (what, why, action))
            what, why = guidance["what"], guidance["why"]
            action = op.guidance_action_text(guidance)
        return InsightCard(
            guidance=guidance,
            insight_id=insight.insight_id,
            category=cat,
            category_label=tp.INSIGHT_CATEGORIES[cat]["label"],
            what_happened=what,
            why_it_matters=why,
            evidence=tuple(str(e) for e in insight.evidence_sources[:6]),
            confidence=op.owner_confidence(insight.confidence),
            recommended_action=action,
            risk=(f"{dq_sev} severity" if dq_sev else insight.trust_level),
            what_would_change_it=changes_it,
            trust=tp.present(insight.trust_level).as_dict(),
            conflict_ids=insight.conflict_ids, dq_ids=insight.dq_ids,
            metric_ids=insight.trigger_metric_ids,
            affected_amount=insight.affected_amount,
            affected_count=insight.affected_count,
            evidence_status=op.evidence_status(insight.dq_ids),
            action_category=action_category,
            action_category_label=osem.ACTION_CATEGORIES[action_category]["label"],
            needs_attention=osem.needs_attention(action_category),
            action_kind=dq_kind,
            ai_entry_points=(
                # The question the owner would type, not the record's identifier.
                {"action": "why", "label": "Why?",
                 "question": (f"Why does {op._joined_names(subjects)} need attention?"
                              if subjects else "Why does this need attention?")},
                {"action": "recommend", "label": "What should I do?",
                 "question": "What should I do?"},
            ),
        )

    def _attention_subjects(self, cards):
        """One entry per business subject in the attention feed.

        Four separate records about tenant dues -- an application balance, a legacy ledger, two
        ledger conventions -- are four findings and ONE thing the owner has to deal with. Shown
        one card each they read as four separate problems, and the four definitions the conflict
        is actually about are already listed together on the measure's own page.

        A group states what its strongest member asks for: a subject holding both a definition
        conflict and a recording problem needs a decision AND a review, and reporting only the
        milder of the two would understate it. Every member is carried on the group, so nothing
        is hidden by the grouping -- only counted once.

        The subject is the same one the decision queue groups by, so a subject cannot appear as
        one card in one list and three in another.
        """
        order, groups = [], {}
        for card in cards:
            subject = op.owner_subject_of(op.owner_subject_names(card.metric_ids, self.registry))
            # A finding touching no measure of its own still belongs somewhere an owner can see
            # it, rather than being dropped for want of a name.
            key = subject or "Across several measures"
            if key not in groups:
                order.append(key)
                groups[key] = []
            groups[key].append(card)

        out = []
        for key in order:
            members = groups[key]
            categories = [c.action_category for c in members]
            strongest = osem.most_demanding(categories) or osem.REVIEW_REQUIRED
            out.append({
                "subject": key,
                "action_category": strongest,
                "action_category_label": osem.ACTION_CATEGORIES[strongest]["label"],
                "needs_attention": osem.needs_attention(strongest),
                "finding_count": len(members),
                # Present when the group holds more than one kind of ask, so a card can say it
                # needs both a decision and a review rather than only the stronger one.
                "categories": tuple(dict.fromkeys(categories)),
                "insight_ids": tuple(c.insight_id for c in members),
                "items": tuple(c.as_dict() for c in members),
            })
        return tuple(out)

    def _dq_monitor_card(self, row):
        """A recorded finding that asks nothing of the owner, as a feed card.

        Built from `dq_owner_card` -- the same projection the register renders -- so the finding
        reads identically in both places. It is not an "insight": no trigger fired and no
        reasoning ladder was walked, and nothing here pretends otherwise. It is the finding, shown
        where an owner will see it.

        The posture is the register's own handling of the finding, unchanged.
        """
        card = self.dq_owner_card(row)
        posture = (row.get("ai_handling") or "").strip().upper()
        return InsightCard(
            insight_id=f"INS.MONITOR.{card['dq_id']}",
            category=tp.CAT_DATA_QUALITY,
            category_label=tp.INSIGHT_CATEGORIES[tp.CAT_DATA_QUALITY]["label"],
            what_happened=card["owner_what"],
            why_it_matters=card["owner_why"],
            recommended_action=card["owner_action"],
            evidence=card["evidence"][:6],
            risk=card["severity"],
            trust=tp.present(posture).as_dict(),
            dq_ids=(card["dq_id"],),
            metric_ids=card["affected_metrics"],
            evidence_status=op.evidence_status((card["dq_id"],)),
            action_category=card["owner_action_category"],
            action_category_label=card["owner_category_label"],
            needs_attention=card["owner_needs_attention"],
            action_kind=card["owner_action_kind"],
        )

    def _change_insight(self, change):
        """A validated period change as a feed item. Direction only -- no claim about size,
        importance, or cause, because none of the three is supported by the evidence."""
        cat = tp.categorise_change(change)
        if cat is None:
            return None
        # A validated movement is a fact about the business, not something waiting on anyone. It
        # used to arrive in the feed's attention bucket, which is how a revenue RISE came to be
        # counted among the things needing attention.
        action_category = osem.change_action_category(change.classification)
        pct = (f" ({abs(change.percentage_change)}%)"
               if change.percentage_change is not None else "")
        direction = "rose" if change.classification == "INCREASE" else "fell"
        return InsightCard(
            insight_id=f"INS.CHANGE.{change.metric_id}",
            category=cat,
            category_label=tp.INSIGHT_CATEGORIES[cat]["label"],
            action_category=action_category,
            action_category_label=osem.ACTION_CATEGORIES[action_category]["label"],
            needs_attention=osem.needs_attention(action_category),
            what_happened=(f"{op.owner_measure_name(change.metric_name)} {direction} by "
                           f"{format_value(abs(change.absolute_change))}{pct} between "
                           f"{op.owner_period_label(change.previous_period)} and "
                           f"{op.owner_period_label(change.current_period)}."),
            why_it_matters=("Both months are complete, so this is a real movement rather than "
                            "a part-month artefact. Whether it is big enough to act on is your "
                            "call: your records set no threshold for that, so none is applied "
                            "here."),
            evidence=tuple(str(e) for e in change.evidence_sources[:6]),
            confidence=("The movement is arithmetic over two complete periods, not an "
                        "estimate."),
            recommended_action="",
            risk=change.trust_level,
            # `materiality` is written for the audit trail and cites the specification clause
            # that leaves the threshold open. Stripping the citation out of it leaves a verb
            # hanging off a colon, so the owner's half of it is said directly. The substance is
            # unchanged: no threshold exists, and none is invented.
            what_would_change_it=op.OWNER_MATERIALITY
            if change.materiality == MATERIALITY_UNDEFINED
            else op.sanitize_owner_text(change.materiality),
            trust=tp.present(change.trust_level).as_dict(),
            conflict_ids=change.conflict_ids, dq_ids=change.dq_ids,
            metric_ids=(change.metric_id,),
            ai_entry_points=(
                {"action": "why", "label": "Why?",
                 "question": f"Why did {change.metric_name} change?",
                 "metric_id": change.metric_id},
            ),
        )

    def _change_card(self, change):
        display = ""
        if change.detected and change.absolute_change is not None:
            # The direction word beside this carries the sign, so the magnitude is unsigned:
            # "fell -221,734.74 (-5.88%)" is a double negative that reads as a rise.
            pct = (f" ({abs(change.percentage_change)}%)"
                   if change.percentage_change is not None else "")
            display = f"{format_value(abs(change.absolute_change))}{pct}"
        return ChangeCard(
            metric_id=change.metric_id, title=op.owner_measure_name(change.metric_name),
            # "INCREASE" and "2026-07-01" are how the engine records a movement. An owner reads
            # "rose" and "July 2026", and the strip is the only place these are shown.
            direction=op.owner_direction(change.classification),
            display_change=display,
            current_period=op.owner_period_label(change.current_period),
            previous_period=op.owner_period_label(change.previous_period),
            # The same three notes the insight card projects, on the strip that renders them
            # beside the movement itself. Left raw they carried the specification clause, the
            # metric record and the composite-series explanation written for an analyst.
            materiality_note=(op.OWNER_MATERIALITY
                              if change.materiality == MATERIALITY_UNDEFINED
                              else op.sanitize_owner_text(change.materiality)),
            coverage_note=op.owner_coverage_note(change.coverage_note),
            unavailable_reason=self._comparison_reason(change),
            trust=tp.present(change.trust_level).as_dict(),
            ai_entry_points=(
                {"action": "why", "label": "Why?",
                 "question": f"Why did {change.metric_name} change?",
                 "metric_id": change.metric_id},
            ),
            partial_note=self._partial_note(change),
            alternative_note=self._alternative_note(change),
            **self._movement_category(change),
            **self._components_of(change),
            **self._compared_figures(change),
        )

    @staticmethod
    def _movement_category(change):
        """A movement's action category, or none where no movement was established.

        A comparison the engine refused -- a part-month, a composite series, an absent month --
        has no direction, so it gets no category rather than a neutral-looking one. Absence of a
        movement is not a movement of zero.
        """
        category = (osem.change_action_category(change.classification)
                    if change.detected else None)
        if category is None:
            return {"action_category": "", "action_category_label": "", "needs_attention": False}
        return {"action_category": category,
                "action_category_label": osem.ACTION_CATEGORIES[category]["label"],
                "needs_attention": osem.needs_attention(category)}

    def _comparison_reason(self, change):
        """Why a requested comparison produced no movement.

        A comparison the analyst asked for and did not get is led with the fact that it is not
        available, before the engine's explanation of why. Without that lead the explanation
        reads as a note about the answer rather than as the answer. The part-month case keeps
        its own wording untouched: it already says exactly this, in more detail, and stacking a
        second refusal above it would say it twice.
        """
        reason = self._as_month_labels(
            op._reason_with_subject(
                op.sanitize_owner_text(change.unavailable_reason), change.metric_name),
            change)
        asked = bool(change.requested_current or change.requested_previous)
        if reason and asked and not change.current_is_partial:
            lead = "This comparison is not available from the exported evidence."
            if not reason.startswith(lead):
                return f"{lead} {reason}"
        return reason

    def _compared_figures(self, change):
        """The two figures a comparison is between, and the movement between them.

        Formatted here, not in the browser: the renderer prints these strings. A composite
        monthly value (P&L carries revenue, expenses and net profit together) has no single
        figure to state, so it gets none -- the card already says why it is not comparable.
        """
        def money(value):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return format_value(value, change.unit or "INR")
            return ""

        if not change.detected:
            return {"current_display": "", "previous_display": "",
                    "absolute_display": "", "percent_display": ""}

        absolute = ""
        if change.absolute_change is not None:
            sign = "+" if change.absolute_change > 0 else "-" if change.absolute_change < 0 else ""
            absolute = sign + format_value(abs(change.absolute_change), change.unit or "INR")
        percent = ("" if change.percentage_change is None
                   else f"{abs(change.percentage_change)}%")
        return {"current_display": money(change.current_value),
                "previous_display": money(change.previous_value),
                "absolute_display": absolute, "percent_display": percent}

    def _components_of(self, change):
        """The movement's parts, said in the owner's words.

        The arithmetic is the decomposition module's and was reconciled there. This adds the
        signs, the money formatting and the sentence that states the relationship between the
        parts and the whole -- and states it as a fact that was checked, not as a claim.
        """
        result = variance.decompose(change)
        if not result.available:
            return {"components": (), "component_basis": "",
                    "component_note": result.unavailable_reason or ""}

        rows = tuple({
            "label": c.label,
            "value": c.change,
            "display_change": ("+" if c.change > 0 else "-" if c.change < 0 else "")
                              + format_value(abs(c.change), "INR"),
            "direction": op.owner_direction(
                "INCREASE" if c.change > 0 else "DECREASE" if c.change < 0 else "NO_CHANGE"),
        } for c in result.components)

        note = (f"These parts add up to the whole of the reported movement "
                f"({format_value(abs(result.total_change), 'INR')}). Each is the same "
                f"recorded amount counted once, so nothing is estimated and nothing is left "
                f"over.")
        if result.caveats:
            note = note + " " + " ".join(op.sanitize_owner_text(c) for c in result.caveats)
        return {"components": rows, "component_basis": result.basis, "component_note": note}

    def _as_month_labels(self, text, change):
        """A sentence with the series keys it names said as months.

        A key is how the series is addressed ("2026-08-01"); a month is what the owner asked
        for. Only the two keys this change actually carries are substituted -- the export
        cut-off date in the same sentence is a real date and stays one.
        """
        out = text or ""
        for key in (change.current_period, change.previous_period):
            if out and key:
                out = out.replace(key, op.owner_period_label(key))
        return out

    def _partial_note(self, change):
        return self._as_month_labels(
            op.sanitize_owner_text(change.partial_coverage_note or ""), change)

    def _alternative_note(self, change):
        """The whole-month comparison the detector attached beside a part-month request.

        It answers a different question from the one asked, so it is labelled as a different
        question. Its figures are the detector's; this only says which months they are for.
        """
        alt = getattr(change, "alternative", None)
        if alt is None or not getattr(alt, "detected", False):
            return ""
        return (f"The nearest whole-month comparison the records support is "
                f"{op.owner_period_label(alt.previous_period)} to "
                f"{op.owner_period_label(alt.current_period)}. It answers a different question "
                f"from the one you asked and is not shown as its answer.")

    # -- metric detail ------------------------------------------------------------------------------

    def metric_detail(self, metric_id):
        """Phase 8 brief 10."""
        if metric_id not in self.registry:
            return {"metric_id": metric_id, "available": False,
                    "unavailable_reason": f"{metric_id!r} is not a semantic metric. "
                                          f"{NOT_DETERMINABLE_TEXT}"}
        spec = self.registry.get(metric_id)
        tile = self.tile(metric_id)
        chain = chain_for(spec)
        answer = self.executor.execute(metric_id)
        first = answer.results[0] if answer.results else None

        related = tuple(d for d in spec.dependency_metrics
                        if d in self.registry and d != "ALL")

        return {
            "metric_id": metric_id,
            "available": True,
            "name": spec.semantic_name,
            "business_definition": spec.definition,
            # The semantic contract, whole. The page leads with the fields the contract itself
            # marks owner-safe and puts the rest under technical details -- rather than the page
            # deciding for itself which registry prose an owner can read.
            "contract": self.metric_contract(metric_id),
            "tile": tile.as_dict(),
            "trust": tile.trust,
            "caveat": spec.caveat_text,
            "period": tile.as_of,
            "dimensions": tuple(d.strip() for d in (spec.dimensions or "").split(";")
                                if d.strip()),
            "calculation": (first.calculation_provenance if first else spec.definition),
            "filters": spec.filters,
            "reversal_policy": spec.reversal_policy,
            "soft_delete_policy": spec.soft_delete_policy,
            "date_field": spec.date_field,
            "evidence": chain.resolved_keys or tuple(
                f"declared source (not exported evidence): {spec.source_objects[:100]}"),
            "validation": {"status": tile.validation_status,
                           "reference": spec.validation_reference},
            "related_metrics": related,
            "conflicts": spec.conflict_ids,
            "dq_issues": spec.dq_ids,
            "insights": tuple(i.insight_id for i in self.insight_engine.generate()
                              if metric_id in i.trigger_metric_ids),
            # The questions are shown to the owner as written, so they are asked in the owner's
            # words. They used to carry the registry name and the record identifier -- "Why did
            # Tenant dues -- Def A: v_outstanding_receivables (reversals excluded) change?" -- as
            # visible button text. The measure is the same one either way; the chat resolves it
            # by name, and every entry point that needs the identifier still carries it as a
            # field rather than inside a sentence.
            "recommended_questions": (
                f"Why did {op.owner_measure_name(spec.semantic_name)} change?",
                f"How was {op.owner_measure_name(spec.semantic_name)} calculated?",
                "What should I investigate next?",
            ),
        }

    # -- conflict view -------------------------------------------------------------------------------

    def conflict_view(self, metric_id):
        """Phase 8 brief 11. Never chooses a winner."""
        spec = self.registry.get(metric_id)
        decision = self.gate.authorize(metric_id)
        answer = self.executor.execute(metric_id)
        pres = tp.present(decision.effective_level)

        definitions = []
        for r in answer.results:
            definitions.append({
                "label": r.definition_label,
                "value": r.value,
                "display_value": format_value(r.value, r.unit),
                "source": ", ".join(str(e) for e in r.evidence_sources[:4]),
                "time_semantics": r.as_of,
                "calculation": r.calculation_provenance[:400],
                "trust": tp.present(answer.trust_level).as_dict(),
                "validation_status": r.validation_status,
                "limitations": r.limitations,
            })

        return {
            "metric_id": metric_id,
            "name": spec.semantic_name,
            "trust": pres.as_dict(),
            "headline_permitted": False,
            "definitions": tuple(definitions),
            "definitions_computable": len(definitions) >= 2,
            "numeric_difference": answer.numeric_difference,
            "conflict_ids": spec.conflict_ids,
            "dq_ids": spec.dq_ids,
            "which_should_we_use": (
                "This requires a business decision, not an analytical one. Each definition below "
                "is evidence-backed and internally consistent; they disagree because they measure "
                "different things. The system will not choose between them, and will keep showing "
                "all of them until an owner decision records which is authoritative."),
            "resolution_owner": "business owner (not the system)",
            # Stated as a field rather than left to be inferred from the posture, so a surface
            # listing "what management must decide" reads the same flag every other surface does.
            "decision_required": decision.effective_level in ("SHOW_BOTH", "BLOCK"),
            "action_category": (osem.DECISION_REQUIRED
                                if decision.effective_level in ("SHOW_BOTH", "BLOCK")
                                else osem.INFORMATIONAL),
            "owner_status": pres.owner_status,
            "note": ("" if len(definitions) >= 2 else
                     f"The competing definitions of this measure are not computable in the "
                     f"current engine, so the conflict is shown without figures rather than "
                     f"implying two comparable numbers exist. {NOT_DETERMINABLE_TEXT}"),
        }

    def unresolved_definitions(self):
        """Every measure whose evidence still carries competing definitions, with what each one
        says and why no winner has been chosen.

        A listing, not a resolution. Nothing here picks, ranks, averages or hides a definition:
        the engine holds them all until an owner decision records which is authoritative, and even
        then that decision names a preference -- it does not delete the evidence behind the others.
        """
        out = []
        for metric_id in self.registry.all_ids():
            level = self.gate.authorize(metric_id).effective_level
            if level not in ("SHOW_BOTH", "BLOCK"):
                continue
            view = self.conflict_view(metric_id)
            out.append({
                "metric_id": metric_id,
                "measure": op.owner_measure_name(self.registry.get(metric_id).semantic_name),
                "owner_status": view["owner_status"],
                "definition_count": len(view["definitions"]),
                "definitions_computable": view["definitions_computable"],
                "decision_required": view["decision_required"],
                "why_no_single_figure": view["which_should_we_use"],
                "resolution_owner": view["resolution_owner"],
            })
        return tuple(out)

    # -- data quality center ---------------------------------------------------------------------------

    def dq_owner_card(self, row):
        """One recorded finding, projected once, for every surface that shows findings.

        The register renders it, Owner Home renders the monitor ones, and anything else that
        needs to say what a finding is reads the same three sentences from the same place. Built
        once here because the alternative -- each surface composing its own -- is exactly how the
        product came to describe the same finding differently depending on where you read it.

        A PROJECTION only: severity, amount, evidence, root cause, status and the posture of every
        measure the finding touches are carried through untouched, and are what the technical
        section renders.
        """
        affected = tuple(m for m in self.registry.all_ids()
                         if row.get("dq_id", "") in self.registry.get(m).dq_ids)
        posture = (row.get("ai_handling") or "").strip().upper()
        names = tuple(dict.fromkeys(
            op.owner_measure_name(self.registry.get(m).semantic_name) for m in affected))
        # What the finding IS, from its own fields -- which is what decides what an owner can do
        # about it. The gate's posture still decides how the measures it touches are presented;
        # it does not decide this sentence.
        kind = _dq_action_kind(row)
        category = osem.dq_action_category(kind)
        what = _dq_owner_issue(row, kind, names)
        return {
            # The owner's three questions, in the order they are asked. Named the same way on
            # every surface that carries a finding, so a card built here and a section built by
            # decision support say the same thing in the same fields.
            "owner_what": what,
            "owner_why": _dq_why(names, row.get("affected_amount", ""), posture),
            "owner_action": osem.dq_owner_action(kind),
            # The classification itself, carried on the payload so a surface can group by it
            # rather than re-deriving it from the words.
            "owner_action_kind": kind,
            "owner_action_category": category,
            "owner_category_label": osem.ACTION_CATEGORIES[category]["label"],
            "owner_needs_attention": osem.needs_attention(category),
            # The name this field had before the three-question shape existed. Kept so an older
            # client does not lose the sentence.
            "owner_issue": what,
            "owner_measure_names": names,
            "owner_posture": _DQ_POSTURE_LABELS.get(posture, ""),
            "severity": (row.get("severity") or "UNVERIFIED").upper(),
            "dq_id": row.get("dq_id", ""),
            "issue": row.get("issue", ""),
            "business_area": row.get("business_area", ""),
            "affected_rows": row.get("affected_rows", ""),
            "affected_amount": row.get("affected_amount", ""),
            "affected_metrics": affected,
            "affected_trust_levels": tuple(
                sorted({self.gate.authorize(m).effective_level for m in affected})),
            "root_cause": row.get("root_cause", ""),
            "root_cause_confidence": row.get("root_cause_confidence", ""),
            "status": row.get("status", ""),
            "evidence": tuple(e.strip() for e in
                              (row.get("evidence_files") or "").split(";") if e.strip()),
            "recommended_investigation": row.get("ai_handling", ""),
        }

    def data_quality_center(self):
        """Phase 8 brief 12.

        The owner-facing sentences added here are a PROJECTION of the fields already present --
        the finding's own text, the measures it touches, and the handling the gate already
        assigned it. No severity, amount, evidence reference or posture is computed, reordered
        or altered; every original field is still on the record beside them, which is what the
        page's technical section renders.
        """
        by_severity = {}
        for row in self.insight_engine.dq_rows:
            sev = (row.get("severity") or "UNVERIFIED").upper()
            by_severity.setdefault(sev, []).append(self.dq_owner_card(row))
        order = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL", "UNVERIFIED")
        every = [i for s in order for i in by_severity.get(s, [])]

        # The same findings counted by what they ASK FOR rather than by how serious they are.
        # Severity says how bad; the action category says who has to do something and what. A page
        # that only ever grouped by severity could not tell an owner that four of their thirty-two
        # findings are waiting on a decision only they can make.
        by_action = {}
        for issue in every:
            by_action.setdefault(issue["owner_action_category"], []).append(issue)

        return {
            "severities": tuple(
                {"severity": s, "count": len(by_severity.get(s, [])),
                 "issues": tuple(by_severity.get(s, []))}
                for s in order if by_severity.get(s)),
            "action_categories": tuple(
                {"category": c,
                 "label": osem.ACTION_CATEGORIES[c]["label"],
                 "meaning": osem.ACTION_CATEGORIES[c]["owner_meaning"],
                 "needs_attention": osem.needs_attention(c),
                 "count": len(by_action[c]),
                 "dq_ids": tuple(i["dq_id"] for i in by_action[c])}
                for c in sorted(by_action, key=osem.category_order)),
            "total": sum(len(v) for v in by_severity.values()),
        }

    def dq_action_kinds(self):
        """Every finding's kind, by its record id.

        One classification, read by whoever needs it -- the DQ page groups by it, the insight feed
        takes its action category from it, and decision support can say what a finding asks for
        without re-deriving anything. Re-deriving is exactly how the surfaces came to disagree.
        """
        return {row.get("dq_id", ""): osem.dq_action_kind(row)
                for row in self.insight_engine.dq_rows if row.get("dq_id")}

    # -- the metric semantic contract ---------------------------------------------------------------

    def metric_contract(self, metric_id):
        """Everything a surface may need to know about what a measure MEANS, in one place.

        Twelve questions, each answered from the registry row and the gate -- never inferred, never
        filled in with something plausible. A field the evidence does not establish says so in the
        product's own words rather than going blank, because a blank field reads as "no limitation"
        and an absent grain reads as "any grain you like".

        Two of the twelve are DERIVED rather than read, and both are derived from decisions that
        already exist: whether a measure may be used for a decision is the gate's headline
        permission, and whether it can be compared over time is the same historical-policy test the
        tiles already use to decide whether to offer a "Why did it change?" button. Neither
        introduces a new judgement.
        """
        if metric_id not in self.registry:
            return {"metric_id": metric_id, "available": False,
                    "reason": f"{metric_id!r} is not a semantic metric. {NOT_DETERMINABLE_TEXT}"}

        spec = self.registry.get(metric_id)
        decision = self.gate.authorize(metric_id)
        pres = tp.present(decision.effective_level)
        conflicted = decision.effective_level in ("SHOW_BOTH", "BLOCK")

        def stated(value):
            """The registry's own words, or the honest sentence where it states nothing."""
            text = str(value or "").strip()
            return text if text else NOT_DETERMINABLE_TEXT

        contract = {
            "metric_id": metric_id,
            "available": True,
            # 1-3: what it is called, what it answers, and how it is defined.
            "business_name": op.owner_measure_name(spec.semantic_name),
            "business_question": stated(spec.description),
            "definition": stated(spec.definition),
            # 4-6: what one row of it is, over what time, and how it can be cut.
            "grain": stated(spec.grain),
            "supported_period": stated(spec.historical_policy),
            "supported_dimensions": stated(spec.dimensions),
            # 7-8: the gate's verdict and the owner's word for it. The canonical level stays.
            "trust_level": decision.effective_level,
            "owner_status": pres.owner_status,
            # An empty caveat is the registry SAYING there is no caveat, and the gate agrees by
            # not requiring one. That is a different fact from "we could not establish whether
            # this measure has a limitation", and reading it as the latter would put a doubt on
            # eighteen measures the evidence is clear about.
            "limitations": (stated(spec.caveat_text)
                            if (spec.caveat_text or "").strip() or decision.caveat_required
                            else "No limitation is recorded against this measure."),
            # 9-10: what happens when definitions compete, and what that asks of the owner.
            "conflict_behaviour": (
                "Every competing definition is shown with its own figure. The system does not "
                "choose between them; only a recorded owner decision can name one as official, "
                "and that decision does not remove the others."
                if conflicted else
                "This measure has one agreed definition, so no competing reading is held for it."),
            "owner_action": (osem.DQ_KINDS[osem.KIND_DEFINITION_CONFLICT]["owner_action"]
                             if conflicted else pres.owner_explanation),
            "action_category": (osem.DECISION_REQUIRED if conflicted else osem.INFORMATIONAL),
            # 11-12: the two questions a surface actually asks before using a measure.
            "usable_for_decisions": bool(decision.headline_permitted),
            "usable_for_decisions_note": (
                "A single figure may be stated for this measure and used on its own."
                if decision.headline_permitted else
                "No single figure may be stated for this measure, so it cannot stand alone in a "
                "decision. What it holds is shown in full instead."),
            "comparable_over_time": self._has_time_series(spec),
            "comparable_over_time_note": (
                "Complete periods can be compared for this measure."
                if self._has_time_series(spec) else
                "The records hold this as a current state rather than a series, so there is "
                "nothing to compare one period against another."),
        }

        # Which of these fields may appear on a DEFAULT owner screen.
        #
        # (The same test decides the tile's `owner_caveat` above: a caveat that names an
        # application object or opens with the posture in machine form is not shown as written.)
        #
        # Several are the registry's own words and are written for the people who maintain the
        # semantic layer: a definition naming an application function, a limitation citing the
        # conflict and finding records behind it. Those are the RIGHT words for the audit trail
        # and the wrong ones for an owner, so rather than editing them -- which this project has
        # learned produces worse English than the identifier it removes -- the contract says which
        # fields survive being read aloud to an owner. A surface renders the safe ones by default
        # and puts the rest under technical details. Nothing is removed from the payload.
        contract["owner_safe_fields"] = tuple(
            name for name in (
                "business_name", "business_question", "definition", "grain", "supported_period",
                "supported_dimensions", "limitations", "conflict_behaviour", "owner_action",
                "owner_status", "usable_for_decisions_note", "comparable_over_time_note")
            if osem.owner_safe(contract[name]))
        return contract

    def metric_contracts(self):
        """The contract for every active measure, in registry order."""
        return tuple(self.metric_contract(m) for m in self.registry.all_ids())

    # -- role workspace ---------------------------------------------------------------------------------

    def role_workspace(self, role_id, home=None):
        """Phase 8 brief 7. Same metrics, same trust -- only the lens changes.

        The movements, the attention queue and the findings are the ones the dashboard already
        built: passed in rather than recomputed, so a workspace cannot disagree with Owner Home
        about what moved or what is waiting on a decision. Every measure the role may see is
        still in `tiles`; ordering them is the page's business, not this method's.
        """
        role = analyst_roles.role(role_id)
        if role is None:
            return {"role_id": role_id, "available": False,
                    "reason": f"{role_id!r} is not a registered analyst role."}
        # What the role MAY see, by its declared domains. Authorization, unchanged.
        authorized = tuple(m for m in self.registry.all_ids()
                           if self.registry.get(m).domain in role.domains)
        # What the workspace is ABOUT, from links the registry records -- a calculator
        # computing a metric, or a working set its specification cites. Never wider than
        # `authorized`, and never a word matched against a description. Every list below is
        # scoped by it, so a decision or a finding about another lens's measures stays there.
        scope = role_scope.workspace_scope(role, authorized)
        metric_ids = scope.scope_ids
        home = home if home is not None else self.owner_home()
        in_scope = set(metric_ids)
        capabilities = set(role.capabilities or ())
        # A lens whose declared capability is surfacing definition conflicts sees every conflict,
        # whichever domain the conflicted measure lives in. Scoping them out by metric id left the
        # Risk / Data-Quality lens without the conflicts it exists to surface. The findings and
        # decisions are the dashboard's own objects; nothing is re-derived.
        surfaces_conflicts = "conflict_surface" in capabilities

        def _in_lens(insight):
            return bool(in_scope & set(insight.metric_ids or ())) or (
                surfaces_conflicts and insight.category == "definition_conflict")

        # A decision raised by a conflict finding is identified by that finding's id.
        conflict_insights = {i.insight_id for i in home.insights
                             if i.category == "definition_conflict"}

        def _decision_in_lens(decision):
            return (not decision.get("metric_ids")
                    or bool(in_scope & set(decision.get("metric_ids") or ()))
                    or (surfaces_conflicts
                        and decision.get("insight_id") in conflict_insights))

        payload = {
            "role_id": role_id,
            "available": True,
            "display_name": role.display_name,
            "focus": role.owner_focus or role.semantic_scope,
            "focus_note": role.owner_focus_note,
            "capabilities": role.capabilities,
            "never_does": role.never_does,
            "tiles": tuple(self.tile(m, role.display_name).as_dict()
                           for m in metric_ids),
            "metric_count": len(metric_ids),
            # What leads, in the role's own capability order. Emphasis only: every id is
            # already in `tiles`.
            "foreground": scope.foreground_ids,
            # Which rule produced the scope, and -- where the records could not narrow this
            # lens -- the owner's sentence saying so. `scope_reason` is for the audit trail.
            "scope_basis": scope.basis,
            "scope_note": scope.note,
            "scope_reason": scope.reason,
            "changes": tuple(_change_dict(c) for c in home.changes
                             if c.metric_id in in_scope),
            # Scoped like every other list in this method. It was not, so an Operations or
            # Risk lens received the same five decisions as everyone -- about tenant dues,
            # owner rent, profit and occupancy, measures outside its own scope. The decision
            # itself is untouched and still shows in full on Owner Home; this only leaves out
            # the ones this lens cannot see the measures for.
            "decision_queue": tuple(d for d in home.decision_queue if _decision_in_lens(d)),
            "insights": tuple(i.as_dict() for i in home.insights if _in_lens(i)),
            # The same three-way split Owner Home renders, narrowed to this lens. A workspace
            # that recomputed the grouping could disagree with the dashboard about whether a
            # movement is work; taking the engine's split means it cannot.
            # `needs_attention` keeps the ranker's order, which is the investigation priority.
            "needs_attention": tuple(i.as_dict() for i in home.needs_attention if _in_lens(i)),
            "movements": tuple(i.as_dict() for i in home.movements if _in_lens(i)),
            "findings": tuple(i.as_dict() for i in home.findings if _in_lens(i)),
            "supporting": tuple(i.as_dict() for i in home.supporting if _in_lens(i)),
            "limitations": tuple(home.limitations),
            "as_of": home.as_of,
        }
        # The owner reads the revenue forecast in one workspace only. Other lenses that hold the
        # capability (Data Scientist, for diagnostics) do not repeat it as an owner display.
        if role_id == analyst_roles.FORECAST_OWNER_ROLE:
            payload["revenue_forecast"] = self.revenue_forecast_panel()
        # Recommended actions are the dashboard's own, attached to findings. A lens that
        # recommends receives the ones whose finding is in its lens -- no action is written here.
        if capabilities & {"recommendation", "attention_required", "pending_decision"}:
            lens_insights = {i["insight_id"] for i in payload["insights"]}
            payload["recommended_actions"] = tuple(
                a for a in home.recommended_actions if a.get("insight_id") in lens_insights)
        # The recorded data-quality register, for the lens that scans it. The same object the
        # Data Quality page and the risk section render.
        if "dq_scan" in capabilities:
            payload["data_quality"] = self.data_quality_center()
        # Model and validation diagnostics for a lens that holds the forecasting capability but is
        # not where the owner reads the forecast. The forecast figures themselves are not repeated.
        if ("revenue_forecast" in capabilities
                and role_id != analyst_roles.FORECAST_OWNER_ROLE):
            payload["forecast_diagnostics"] = self.forecast_diagnostics()
        if "descriptive_analysis" in capabilities:
            payload["descriptive"] = self.descriptive_panel()
        return payload

    # Horizons the diagnostics report, the three the forecaster's own validation documents.
    DIAGNOSTIC_HORIZONS = (1, 3, 6)

    def forecast_diagnostics(self):
        """How the production forecast model was validated. Computes nothing new.

        Every figure is read off `forecasting.forecast_revenue` -- its walk-forward model
        comparison, its per-horizon backtest against the naive benchmark, its drivers and its
        stated configuration. No projection value is carried: those belong to the forecast's
        owner-facing workspace.
        """
        from engine import forecasting as fc

        runs = {h: fc.forecast_revenue(h) for h in self.DIAGNOSTIC_HORIZONS}
        first = runs[self.DIAGNOSTIC_HORIZONS[0]]
        if not first.available:
            return {"available": False,
                    "unavailable_reason": first.not_determinable_reason or ""}
        comparison = first.model_comparison or {}
        models = comparison.get("models") or {}
        return {
            "available": True,
            "owner_workspace": analyst_roles.FORECAST_OWNER_ROLE,
            "metric_id": self.FORECAST_METRIC_ID,
            "target": fc.REVENUE_TARGET,
            "method": first.method,
            "production_model": comparison.get("production_model", ""),
            "ridge_alpha": (first.backtest or {}).get("ridge_alpha"),
            "features": tuple(first.features),
            "design": comparison.get("design", ""),
            "validation_months": tuple(comparison.get("validation_months") or ()),
            "most_accurate_by_mape": comparison.get("most_accurate_by_mape", ""),
            "models": tuple(
                {"model": name, "label": m.get("label", name),
                 "production": name == comparison.get("production_model"),
                 "mae": m.get("MAE"), "rmse": m.get("RMSE"),
                 "mape_pct": m.get("MAPE_pct"), "r2": m.get("R2")}
                for name, m in models.items()),
            "horizons": tuple(
                {"horizon": h, "available": runs[h].available,
                 "mape_pct": (runs[h].backtest or {}).get("mape_pct"),
                 "naive_mape_pct": ((runs[h].backtest or {}).get("compared_against") or {})
                 .get("naive_last_value_mape_pct"),
                 "folds": (runs[h].backtest or {}).get("folds")}
                for h in self.DIAGNOSTIC_HORIZONS),
            "drivers": tuple(first.drivers or ()),
            "interval_basis": first.interval_basis,
            "note": ("The production model stays in use even where a benchmark was more "
                     "accurate on these months; the comparison is reported, not acted on. The "
                     "forecast figures are presented in the Financial Analyst workspace."),
        }

    def descriptive_panel(self):
        """The descriptive summaries the descriptive module defines, in owner wording.

        Only the series and the pairs `engine/descriptive.py` itself names. Each summary is that
        module's output, worded by the same presenter a descriptive question uses.
        """
        from types import SimpleNamespace
        from engine import descriptive

        out = []
        for name in sorted(descriptive.SERIES_METRICS):
            summary = descriptive.series_summary(name)
            out.append({"kind": "series", "name": name, "label": summary.label,
                        "available": summary.available,
                        "text": op.present_descriptive(summary, SimpleNamespace(kind="series"))})
        for first, second in sorted(descriptive.RELATIONSHIPS):
            summary = descriptive.relationship(first, second)
            out.append({"kind": "relationship", "name": f"{first}|{second}",
                        "label": summary.label, "available": summary.available,
                        "text": op.present_descriptive(
                            summary, SimpleNamespace(kind="relationship"))})
        return tuple(out)

    # The forecast's target metric: invoiced revenue, the same attribution the question pipeline
    # gives a forecast answer.
    FORECAST_METRIC_ID = "M.INV.001"

    def revenue_forecast_panel(self):
        """The production invoiced-revenue forecast, shaped for a chart. Computes nothing.

        The projection, its band, its tested error and its limitations are the output of
        `forecasting.forecast_revenue` -- the same call every forecast answer makes. The history
        is `forecasting.monthly_revenue_series`, the exact series that forecast was fitted on, so
        the recorded line and the projected line are one measure. Trust is the gate's posture for
        the forecast's metric, as it is on a forecast answer.
        """
        from engine import forecasting as fc

        forecast = fc.forecast_revenue(fc.MAX_HORIZON)
        level = (self.gate.authorize(self.FORECAST_METRIC_ID).effective_level
                 if forecast.available else "NOT_DETERMINABLE")
        panel = {
            "available": bool(forecast.available),
            "metric_id": self.FORECAST_METRIC_ID,
            "measure": "Invoiced revenue",
            "target": fc.REVENUE_TARGET,
            "trust": tp.present(level).as_dict(),
            "basis_note": (
                "This is a forecast of invoiced revenue: the total of invoices raised for each "
                "billing month. It is not the revenue recorded in the accounts, which is a "
                "different measure with different monthly figures."),
            "unavailable_reason": forecast.not_determinable_reason or "",
        }
        if not forecast.available:
            return panel

        history = tuple((period, value) for period, value in fc.monthly_revenue_series()
                        if forecast.training_start <= period <= forecast.training_end)
        panel.update({
            "method": forecast.method,
            "horizon": forecast.horizon,
            "last_actual_period": forecast.training_end,
            "boundary_note": (
                f"Months up to {op.owner_period_label(forecast.training_end)} are recorded "
                f"invoiced revenue. Months after it are projections: none of them has happened "
                f"yet."),
            "history": tuple({"period": period, "value": value,
                              "display": format_value(value, "INR")}
                             for period, value in history),
            "points": tuple({"period": p.period, "value": p.value,
                             "lower": p.lower, "upper": p.upper,
                             "display": format_value(p.value, "INR"),
                             "lower_display": format_value(p.lower, "INR"),
                             "upper_display": format_value(p.upper, "INR")}
                            for p in forecast.points),
            "interval_basis": forecast.interval_basis,
            "backtest_mape_pct": (forecast.backtest or {}).get("mape_pct"),
            "limitations": tuple(forecast.limitations),
        })
        return panel

    # -- analytics sections (Phase 14) -------------------------------------------------------------

    def analytics_sections(self):
        """The four owner-facing analytics sections and how much each holds.

        A directory only. It reports counts so the navigation can be honest about an empty
        section instead of inviting the owner into one.
        """
        out = []
        for key in cd.SECTIONS:
            title, domain, purpose = cd.SECTION_SPEC[key]
            metric_ids = self._domain_metric_ids(domain)
            caps = self.capabilities.for_section(key)
            out.append({
                "section": key,
                "title": title,
                "purpose": purpose,
                "metric_count": len(metric_ids),
                "supported_capabilities": len(caps["supported"]),
                "declared_limitations": len(caps["limitations"]),
            })
        return {"sections": tuple(out)}

    # An apartment holding one recorded bed is one observation. It is shown -- omitting it would
    # hide a real apartment -- but it is not offered as a comparison, because a single reading
    # cannot be compared against a spread.
    MIN_GROUP = 2

    def apartment_breakdown(self, apartment=""):
        """Apartments and the beds recorded as occupied in each, from the rent metric's rows.

        Every figure here is a rent the records hold, shown as recorded. No average, no rate and
        no apartment-level rent is derived: the evidence carries several different rents inside
        one apartment, so a single figure for the apartment would be one chosen by whoever wrote
        the aggregation rather than one the records contain. What is counted is beds, and what is
        shown is the rents themselves.
        """
        try:
            rows = rent_calc.current_rent_rows(apartment or None)
        except Exception:
            return {"available": False, "apartments": (),
                    "unavailable_reason": NOT_DETERMINABLE_TEXT}

        if apartment and not rows:
            known = set()
            try:
                known = rent_calc.known_apartment_codes()
            except Exception:
                pass
            reason = (f"There is no apartment {apartment!r} in the exported records."
                      if apartment.upper() not in known else
                      f"Apartment {apartment.upper()} has no bed currently occupied, so no rent "
                      f"is in force for it.")
            return {"available": False, "apartments": (), "unavailable_reason": reason}

        grouped = {}
        for row in rows:
            grouped.setdefault(row["apartment"], []).append(row)

        out = []
        for code in sorted(grouped):
            beds = sorted(grouped[code], key=lambda r: r["bed"])
            recorded = [b["rent"] for b in beds if b["rent"] is not None]
            out.append({
                "apartment": code,
                "beds": tuple({
                    "bed": b["bed"],
                    "rent_display": (format_value(b["rent"], "INR") + " a month"
                                     if b["rent"] is not None else ""),
                    "note": ("" if b["rent"] is not None
                             else "No rent is recorded against this bed."),
                } for b in beds),
                "bed_count": len(beds),
                "bed_count_display": f"{len(beds)} occupied bed"
                                     + ("" if len(beds) == 1 else "s"),
                "rent_range_display": (
                    "" if not recorded else
                    format_value(min(recorded), "INR") if min(recorded) == max(recorded)
                    else f"{format_value(min(recorded), 'INR')} to "
                         f"{format_value(max(recorded), 'INR')}"),
                "comparable": len(beds) >= self.MIN_GROUP,
                "note": ("" if len(beds) >= self.MIN_GROUP else
                         "Insufficient data for a reliable comparison: one occupied bed is "
                         "recorded here, so its rent describes that bed and not the apartment."),
            })
        return {
            "available": True,
            "apartments": tuple(out),
            "unavailable_reason": "",
            "basis": ("Beds recorded as currently occupied, with the rent recorded on each. "
                      "Rent is held per bed, so no single apartment rent is stated."),
        }

    def _comparison_modes(self, period, months, partial):
        """Which comparison the evidence can actually serve for the selected month.

        A mode is offered only when the month it would compare against is IN the recorded
        series. "Same month last year" is not offered because year-on-year is a familiar chart
        in other tools; it is offered when that month exists here, and withheld with a reason
        when it does not. The engine still decides what the pair produces -- a mode being
        offered says the month exists, not that the comparison will yield a movement.
        """
        recorded = set(months)

        def shifted(back):
            if not period:
                return ""
            year, month = int(period[:4]), int(period[5:7])
            total = year * 12 + (month - 1) - back
            return f"{total // 12}-{total % 12 + 1:02d}"

        modes = []
        for key, label, back in (("previous", "Previous month", 1),
                                 ("last_year", "Same month last year", 12)):
            target = shifted(back)
            if not period:
                modes.append({"key": key, "label": label, "period": "", "available": False,
                              "unavailable_reason": "Choose a period first."})
            elif target in recorded:
                modes.append({"key": key, "label": label, "period": target, "available": True,
                              "unavailable_reason": ""})
            else:
                modes.append({
                    "key": key, "label": label, "period": target, "available": False,
                    "unavailable_reason": (
                        f"{op.owner_period_label(target)} is not one of the months your records "
                        f"cover, so there is nothing to compare against.")})
        modes.append({"key": "custom", "label": "Choose a month", "period": "",
                      "available": True, "unavailable_reason": ""})
        modes.append({"key": "none", "label": "No comparison", "period": "",
                      "available": True, "unavailable_reason": ""})
        # Said once, where the choice is made, rather than discovered after applying it.
        for mode in modes:
            if mode["period"] and mode["period"] in partial:
                mode["note"] = (f"{op.owner_period_label(mode['period'])} is only recorded "
                                f"part-way through.")
        return tuple(modes)

    def filter_options(self, period=""):
        """What the analyst may actually choose, read off the engine rather than assumed.

        The months are the months a comparable monthly metric has a series for, split by the
        change detector's OWN completeness rule -- so a part-month is offered as a part-month
        and never quietly omitted. The apartments are the codes the export contains, from the
        same resolver the rent metric uses to reject an unknown one.
        """
        months = set()
        for mid in COMPARABLE_MONTHLY_METRICS:
            answer = self.executor.execute(mid)
            for result in answer.results:
                if isinstance(result.value, dict):
                    months.update(k[:7] for k in result.value
                                  if isinstance(k, str) and len(k) >= 7 and k[4] == "-")
        ordered = sorted(months)
        complete, partial = cd_detect._complete_months(ordered)

        try:
            apartments = sorted(rent_calc.known_apartment_codes())
        except Exception:
            apartments = []

        return {
            "months": tuple(ordered),
            "complete_months": tuple(complete),
            "partial_months": tuple(partial),
            "apartments": tuple(apartments),
            "comparison_modes": self._comparison_modes(period, ordered, set(partial)),
            # Stated once, in the bar, instead of on twenty tiles that would each repeat it.
            "apartment_note": (
                "Only measures whose records are held per apartment can be narrowed to one. "
                "Any measure that cannot says so in place of its figure rather than showing "
                "the estate-wide number under an apartment heading."),
        }

    def _domain_metric_ids(self, domain):
        if domain is None:
            return ()
        return tuple(m for m in self.registry.all_ids()
                     if self.registry.get(m).domain == domain)

    def analytics_section(self, section_key, home=None, filters=None):
        """One analytics section, assembled from surfaces that already exist.

        Deliberately NOT a second analytics path. Tiles come from `self.tile()`, insights and
        changes are sliced out of the same `owner_home()` payload the dashboard renders, and
        data-quality findings come from `data_quality_center()`. A figure shown here is the
        same object the dashboard shows, so the two cannot drift apart and disagree.

        `filters` narrows that same path rather than adding another one:

          * `apartment` becomes the calculator kwarg the executor already validates -- honoured
            by a metric whose grain carries it, refused in the executor's own words by one whose
            grain does not.
          * `period`/`compare` become the two arguments `ChangeDetector.detect` already takes,
            so a requested pair keeps every rule that path carries: no silent substitution of a
            different month, the part-month state reported as itself, and a complete-month
            comparison offered as a labelled alternative rather than as the answer.

        Nothing is computed here. The Trust Gate runs before execution exactly as it does
        unfiltered, so a filter can change which records a figure covers and never what posture
        it carries.
        """
        if section_key not in cd.SECTION_SPEC:
            return {"section": section_key, "available": False,
                    "reason": f"{section_key!r} is not an analytics section. "
                              f"Known: {list(cd.SECTIONS)}."}

        filters = _clean_filters(filters)
        title, domain, purpose = cd.SECTION_SPEC[section_key]
        home = home if home is not None else self.owner_home()
        metric_ids = self._domain_metric_ids(domain)
        in_domain = set(metric_ids)

        tile_kwargs = ({"apartment_code": filters["apartment"]}
                       if filters.get("apartment") else {})
        tiles = tuple(self.tile(m, title, **tile_kwargs).as_dict() for m in metric_ids)

        if domain is None:
            # The cross-cutting section reasons across every domain, so it scopes nothing out.
            insights = tuple(i.as_dict() for i in home.insights)
            changes = tuple(_change_dict(c) for c in home.changes)
        else:
            insights = tuple(i.as_dict() for i in home.insights
                             if in_domain & set(i.metric_ids or ()))
            changes = tuple(_change_dict(c) for c in home.changes
                            if c.metric_id in in_domain)

        if filters.get("period") or filters.get("compare"):
            requested = tuple(
                self._change_card(self.detector.detect(
                    mid, current_period=filters.get("period"),
                    previous_period=filters.get("compare")))
                for mid in COMPARABLE_MONTHLY_METRICS
                if domain is None or mid in in_domain)
            changes = tuple(_change_dict(c) for c in requested)

        if filters.get("apartment"):
            # An apartment-scoped view answers apartment-scoped questions. A measure the records
            # do not hold per apartment cannot answer one, so it is OMITTED rather than shown
            # refusing: a screen of refusals is not a narrower answer, it is the same screen
            # with the figures removed and an explanation put in their place.
            #
            # This is a SCOPING decision, the same kind the role filter already makes, and it
            # touches nothing else: a measure that survives keeps the posture, the figure and
            # the caveat it would have had. Nothing is widened -- an omitted measure is never
            # replaced by its estate-wide value -- and nothing is invented, so a measure with no
            # posting against this apartment is omitted rather than shown as a zero.
            tiles = tuple(t for t in tiles if _answers_a_scoped_question(t))
            # A movement CAN be narrowed where the underlying series is held per apartment. That
            # is the revenue series, and the comparison runs through the same change detector
            # every other movement uses -- same interval rules, same part-month refusal, same
            # figures -- with the apartment handed to the metric's own calculator. Nothing is
            # computed here, and the estate series is never shown under an apartment heading.
            #
            # The standing findings and the decisions drawn from them carry no apartment
            # attribution at all, so what remains is the movement's own finding.
            # Which series can be compared at apartment grain is DERIVED, not listed: a metric
            # qualifies when its calculator accepts the narrowing and the registry declares it
            # aggregates per month. A metric registered later with both facts becomes comparable
            # here on its own, with nothing to remember to update.
            comparable = cd_detect.comparable_metrics_for("apartment", self.registry)
            detected = tuple(
                self.detector.detect(
                    mid, current_period=filters.get("period") or None,
                    previous_period=filters.get("compare") or None,
                    apartment_code=filters["apartment"])
                for mid in comparable
                if domain is None or mid in in_domain)
            # A movement the records could not produce for this apartment is left out, like any
            # other measure that could not answer. A part-month request is kept: it says
            # something true about the months asked for.
            usable = tuple(c for c in detected if c.detected or c.current_is_partial)
            changes = tuple(_change_dict(self._change_card(c)) for c in usable)
            insights = tuple(card.as_dict() for card in
                             (self._change_insight(c) for c in usable) if card is not None)

        # One heading per measure. Each tile is named on its own, so the four tenant-dues
        # definitions and the two collections readings arrive under the same owner name and render
        # as the same card repeated. Where names collide within this section, each colliding tile
        # carries its own qualifier from the registry name; every other tile keeps its name.
        # Naming only: no tile is added, dropped, merged or re-postured.
        semantic = [self.registry.get(t["metric_id"]).semantic_name for t in tiles]
        tiles = tuple(
            dict(t, business_name=name) if name != op.owner_measure_name(sem) else t
            for t, sem, name in zip(tiles, semantic, op.distinct_measure_names(semantic)))

        # Conflicts and data-quality findings that actually touch this section's metrics. Both
        # are read off the tiles, so a metric cannot appear clean here and conflicted elsewhere.
        conflict_ids, dq_ids = set(), set()
        for t in tiles:
            conflict_ids.update(t.get("conflict_ids") or ())
            dq_ids.update(t.get("dq_ids") or ())

        payload = {
            "section": section_key,
            "available": True,
            "title": title,
            "purpose": purpose,
            "as_of": home.as_of,
            "tiles": tiles,
            "metric_count": len(tiles),
            "insights": insights,
            "changes": changes,
            "conflict_ids": tuple(sorted(conflict_ids)),
            "dq_ids": tuple(sorted(dq_ids)),
            "trust_summary": _trust_breakdown(tiles),
            "capabilities": self.capabilities.for_section(section_key),
            "limitations": tuple(home.limitations),
            "applied_filters": filters,
            "filter_options": self.filter_options(filters.get("period", "")),
        }

        if section_key == cd.SECTION_INSIGHTS and filters.get("apartment"):
            # The insights section owns no metric domain, so under an apartment filter it would
            # hold only the comparisons -- and an apartment whose series cannot support the
            # requested pair would leave the page bare. The apartment-grained measures that DID
            # answer are carried here too, so the page shows what the records hold for this
            # apartment rather than nothing at all. Same tiles, same postures, same figures as
            # the sections they come from.
            scoped = []
            for other in (cd.SECTION_FINANCIAL, cd.SECTION_OPERATIONS):
                for mid in self._domain_metric_ids(cd.SECTION_SPEC[other][1]):
                    tile = self.tile(mid, title, **tile_kwargs).as_dict()
                    if _answers_a_scoped_question(tile):
                        scoped.append(tile)
            payload["tiles"] = tuple(scoped)
            payload["metric_count"] = len(scoped)
            payload["trust_summary"] = _trust_breakdown(scoped)

        if section_key == cd.SECTION_OPERATIONS:
            # The one dimension this export carries below the estate. It travels with the
            # apartment filter, so choosing an apartment in the bar IS the drill-down.
            payload["apartment_breakdown"] = self.apartment_breakdown(
                filters.get("apartment", ""))

        if section_key == cd.SECTION_RISK and not filters.get("apartment"):
            # The risk section is where data-quality findings BELONG, rather than being a
            # separate screen the owner has to know to visit. They carry no apartment
            # attribution, so an apartment-scoped view leaves them out rather than implying
            # they are that apartment's.
            payload["data_quality"] = self.data_quality_center()

        if section_key == cd.SECTION_INSIGHTS:
            # The queue is drawn from estate-wide findings and carries no apartment attribution,
            # so under an apartment filter it is omitted with the findings it summarises rather
            # than shown as though it were about that apartment.
            scoped = bool(filters.get("apartment"))
            payload["decision_queue"] = () if scoped else tuple(home.decision_queue)
            payload["recommended_actions"] = (
                () if scoped else tuple(home.recommended_actions))

        return payload


def _change_dict(card):
    return {"metric_id": card.metric_id, "title": card.title, "direction": card.direction,
            "display_change": card.display_change, "current_period": card.current_period,
            "previous_period": card.previous_period,
            "materiality_note": card.materiality_note, "coverage_note": card.coverage_note,
            "unavailable_reason": card.unavailable_reason, "trust": card.trust,
            "ai_entry_points": list(card.ai_entry_points),
            "partial_note": card.partial_note,
            "alternative_note": card.alternative_note,
            "components": [dict(c) for c in card.components],
            "component_note": card.component_note,
            "component_basis": card.component_basis,
            "current_display": card.current_display,
            "previous_display": card.previous_display,
            "absolute_display": card.absolute_display,
            "percent_display": card.percent_display}


def _trust_breakdown(tiles):
    """How many of this section's measures sit at each trust level.

    Counting only. The level itself is whatever the gate already put on the tile.
    """
    counts = {}
    for t in tiles:
        level = (t.get("trust") or {}).get("trust_level") or ""
        counts.setdefault(level, {"count": 0, **(t.get("trust") or {})})
        counts[level]["count"] = counts[level]["count"] + 1
    return counts
