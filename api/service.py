"""
service.py -- Phase 9 (W1). The HTTP service boundary.

The only door between a client and the engine. It routes and serialises; it computes nothing.

Two structural properties, both checked by the Phase 9 validator:

1. **No request shape can ask for a computation.** There is no filter language, no formula
   parameter, no query endpoint. A client may name a metric_id, a role_id, a catalogued
   dimension, or ask a natural-language question. That is the entire input surface, so there is
   no way to make the service compute something the engine did not already define.

2. **No response can carry a headline the gate forbade.** Payloads are the Phase 8 view models,
   in which a BLOCK tile has no `value` field at all. The refusal travels as an absence, not as
   a flag a client could ignore.

Trust is re-read from the gate on every request. Values may be cached; trust may not -- a stale
trust posture is a correctness failure, not a stale number.
"""
import logging
import os
import re
import uuid
from dataclasses import asdict, is_dataclass

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.execution import MetricExecutor
from engine.view_models import ViewModelBuilder
from engine import view_models as vm
from engine import capability_disclosure as cd
from engine.analyst_intelligence import AnalystIntelligence
from engine import analyst_intelligence as ai_mod
from engine.executive_summary import render as render_summary
from engine import analyst_roles, trust_presentation as tp
from engine import owner_presentation as op
from engine import explainability
from engine.result import NOT_DETERMINABLE_TEXT

from api.authorization import Authorizer, Session, AuthorizationError, ROLE_OWNER
from api.conversation_store import ConversationStore, DEFAULT_DB
from api.decision_store import decision_store, STATUSES, STATUS_LABELS
from api.provider_config import (ProviderConfig, build_provider, available_adapters,
                                 config_from_env, MODE_HTTP)
from engine import narrative
from engine.llm_provider import LLMUnavailable
from api import data_source as ds
from api import auth as auth_mod
from api import security as sec
from api.observability import Observability, OBS

API_VERSION = "1.0.0"

# The Local LLM narrative layer lives in `engine/narrative.py`. These names are kept for callers
# that read them from the service.
NARRATIVE_METRICS = narrative.WHY.enabled_metrics
NARRATIVE_TIMEOUT_SECONDS = narrative.WHY.timeout_seconds
NARRATIVE_MAX_TOKENS = narrative.WHY.max_tokens
NARRATIVE_FALLBACK_NOTE = narrative.FALLBACK_NOTE

_LOG = logging.getLogger(__name__)


# A breakdown key that is a month, as opposed to one that is a bed or an expense category.
_MONTH_KEY = re.compile(r"^\d{4}-\d{2}")

# The gate's own vocabulary, as it appears in a breakdown key or inside a sentence written for
# the audit trail. One measure counts metrics BY trust level, so its keys are these tokens; and
# an engine limitation names the level it is about. Neither is the owner's language.
_POSTURE_WORDS = ("SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE")
_POSTURE_SENTENCE = re.compile(
    r"\bThis metric's trust level is (?:" + "|".join(_POSTURE_WORDS) + r")\s*:\s*",
    re.IGNORECASE)


def _owner_label_for(text):
    """A breakdown key in the owner's words. A trust token becomes the label the badge uses."""
    key = str(text or "").strip()
    if key.upper() in _POSTURE_WORDS:
        return tp.present(key.upper()).owner_label
    return op.sanitize_owner_text(key)


# A registry definition label that still names an implementation detail after sanitising -- a
# column test like "bed.status=Live", or any leftover `key=value`. The UI has business names for
# these; an export must not invent a different one, so it numbers the definition instead. The
# figures beside it are unchanged and every definition is still exported.
_IMPLEMENTATION_LABEL = re.compile(r"[A-Za-z0-9_]+\.[A-Za-z0-9_]+|=")


def _export_definition_label(raw, index):
    label = op.sanitize_owner_text(op.owner_definition_label(raw or ""))
    if not label or _IMPLEMENTATION_LABEL.search(label):
        return f"Definition {index}"
    return label


def _export_definition_value(text):
    """A composite definition value with its parts named in words rather than field names."""
    parts = []
    for chunk in str(text or "").split(";"):
        piece = chunk.strip()
        if ":" in piece:
            key, _, value = piece.partition(":")
            name = key.strip().replace("_", " ").strip()
            if name:
                name = name[0].upper() + name[1:]
            parts.append(f"{name}: {value.strip()}")
        elif piece:
            parts.append(piece)
    return "; ".join(parts)


def _owner_note(text):
    """An engine note for the owner: the posture clause it opens with is what the trust column
    beside it already says, in words the owner can read."""
    return op.sanitize_owner_text(_POSTURE_SENTENCE.sub("", str(text or "")))


def _plain(obj):
    """Recursively convert dataclasses/tuples into JSON-safe structures."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return _plain(asdict(obj))
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


class AnalyticsService:
    """The service layer. Framework-agnostic, so it is testable without an HTTP client and so
    the routing layer stays a thin adapter."""

    def __init__(self, registry: SemanticRegistry = None, db_path=DEFAULT_DB,
                 provider_config: ProviderConfig = None, source: ds.DataSource = None,
                 authenticator: auth_mod.Authenticator = None,
                 observability: Observability = None):
        self.registry = registry or SemanticRegistry()
        self.gate = TrustGate(self.registry)
        self.executor = MetricExecutor(registry=self.registry, gate=self.gate)
        self.vb = ViewModelBuilder(self.registry, self.gate, self.executor)
        self.authorizer = Authorizer(self.registry)
        self.store = ConversationStore(db_path)
        # SQLite on a machine with a disk; the managed database when DATABASE_URL names one.
        # Same model, same statuses, same contract -- only the place the row is kept differs.
        self.decisions = decision_store(db_path)
        self.provider_config = provider_config or config_from_env()
        self.authenticator = authenticator or auth_mod.authenticator_from_env()
        self.obs = observability or OBS

        # The data source must pass the quarantine gate before it may serve the engine.
        self.source = source or ds.ExportDataSource()
        self.revalidation = ds.RevalidationHarness(self.registry, self.gate, self.executor)
        self._report = self.revalidation.run(self.source)
        ds.bind_source(self.source, self._report)

        self.live = ds.LiveDataSource()
        if (os.environ.get("AI_ANALYTICS_LIVE_ENABLE") or "").strip().lower() == "true":
            self.live = ds.LiveDataSource.from_env(
                as_of=os.environ.get("AI_ANALYTICS_LIVE_AS_OF", ""))
        self._live_report = self.revalidation.run(self.live)
        if self._live_report.passed:
            try:
                ds.bind_source(self.live, self._live_report)
                from engine.evidence_loader import bind_trusted_source
                bind_trusted_source(self.live)
                self.source = self.live
                self._report = self._live_report
                self.obs.inc("source.revalidation_pass")
            except ds.QuarantineError:
                self.obs.note_quarantine()
        else:
            self.obs.note_quarantine()
            self.obs.inc("source.revalidation_fail")

        self._ai = None

        # Memoised engine payloads. See `_memo`.
        self._cache = {}

    # -- payload memoisation --------------------------------------------------------------------
    #
    # The owner-home computation walks 49 metrics, the insight engine, change detection and the
    # executive summary, and takes tens of seconds. Recomputing it per request made the product
    # unusable, and every page paid the cost again.
    #
    # Memoising it is sound rather than merely convenient: the bound evidence is an IMMUTABLE
    # export whose SHA-256 is pinned, so these payloads are a pure function of the source. The
    # key is the source's own descriptor, so the moment the bound source changes -- including
    # the eventual read-only Supabase activation -- every entry is discarded rather than
    # serving a figure computed from the previous source.
    #
    # What is deliberately NOT cached: anything role-dependent. Only the UNFILTERED payload is
    # stored, and authorization is applied to a copy on every request. Caching a filtered
    # payload would risk serving one role's view to another, which is a security failure rather
    # than a stale number.

    def _source_fingerprint(self):
        d = self.source.descriptor()
        return (d.name, d.kind, d.status, d.as_of)

    def _memo(self, key, build):
        fingerprint = self._source_fingerprint()
        if self._cache.get("__source__") != fingerprint:
            self._cache = {"__source__": fingerprint}
        if key not in self._cache:
            self._cache[key] = build()
        return self._cache[key]

    def invalidate_cache(self):
        """Drop every memoised payload. Called when the bound source is replaced."""
        self._cache = {}

    def _home_vm(self):
        """The OwnerHome view model itself, memoised.

        Every analytics section is a slice of this one object, so building it once is what
        stops the dashboard and the four sections from running the insight engine, change
        detection and the executive summary five separate times -- and is also why a figure on
        a section can never disagree with the same figure on the dashboard.
        """
        return self._memo("owner_home_vm", lambda: self.vb.owner_home())

    def warm_cache(self):
        """Build every memoised payload up front.

        Called by the server at startup so the owner's first page is fast rather than paying
        for the whole engine. Not called from `__init__`: a test or a script that only needs
        one metric should not compute the entire business.
        """
        self.owner_home()
        self.metrics()
        self.data_quality()
        self.analytics_sections()
        for key in cd.SECTIONS:
            self.analytics_section(key)
        return sorted(k for k in self._cache if not k.startswith("__"))

    # -- lazily built so a request path that never asks a question never builds an LLM client --
    def _analyst(self):
        if self._ai is None:
            self._ai = AnalystIntelligence(
                registry=self.registry,
                provider=build_provider(self.provider_config),
                verbalize=self.provider_config.verbalize)
        return self._ai

    # -- system ---------------------------------------------------------------------------------

    def health(self):
        desc = self.source.descriptor()
        live = self.live.descriptor()
        return {
            "status": "ok",
            "api_version": API_VERSION,
            "metrics": len(self.registry.all_ids()),
            "data_source": {"name": desc.name, "kind": desc.kind, "status": desc.status,
                            "as_of": desc.as_of, "notes": desc.notes,
                            "remaining_requirement": desc.remaining_requirement},
            "revalidation": {"passed": self._report.passed,
                             "summary": self._report.summary()},
            "live_data": {
                "name": live.name, "kind": live.kind, "status": live.status,
                "as_of": live.as_of, "notes": live.notes,
                "remaining_requirement": (
                    live.remaining_requirement or self._live_report.remaining_requirement
                    or ("" if self._live_report.passed else self._live_report.notes)),
                "revalidation": {"passed": self._live_report.passed,
                                 "summary": self._live_report.summary(),
                                 "divergences": list(self._live_report.divergences)[:12],
                                 "owner_decisions": list(
                                     self._live_report.required_owner_decisions)[:12]},
            },
            "llm": self.provider_config.describe(),
            "auth": self.authenticator.describe(),
            "observability": {"counters": self.obs.snapshot()},
        }

    def llm_adapters(self):
        return {"adapters": list(available_adapters()),
                "active": self.provider_config.describe(),
                "note": ("A credential present in the environment does NOT enable an adapter. "
                         "Activation requires explicit configuration by the deployment.")}

    def trust_summary(self):
        buckets = {}
        for mid in self.registry.all_ids():
            lvl = self.gate.authorize(mid).effective_level
            buckets.setdefault(lvl, []).append(mid)
        return {"levels": [
            {**tp.present(lvl).as_dict(), "count": len(ids), "metric_ids": sorted(ids)}
            for lvl, ids in sorted(buckets.items())]}

    # -- owner surfaces ---------------------------------------------------------------------------

    def owner_home(self, role_id=ROLE_OWNER):
        self.authorizer.resolve(role_id)
        # A SHALLOW copy is taken before filtering: `_filter_payload` replaces top-level keys
        # with new lists and never mutates a tile, so the cached payload stays intact while the
        # caller gets a payload filtered for their own role.
        home = dict(self._memo("owner_home", lambda: _plain(self._home_vm())))
        return self._filter_payload(home, role_id)

    def _visible(self, role_id):
        return set(self.authorizer.filter_metrics(role_id))

    def _filter_payload(self, home, role_id):
        vis = self._visible(role_id)
        for key in ("business_health", "operations", "risks"):
            home[key] = [t for t in home.get(key, []) if t.get("metric_id") in vis]
        # The undivided feed and the three groups the engine split it into are filtered by the
        # same rule, so a role cannot see an item in one list that was withheld from another.
        for key in ("insights", "needs_attention", "movements", "findings", "supporting"):
            home[key] = [i for i in home.get(key, [])
                         if vis.issuperset(i.get("metric_ids") or ())]
        home["changes"] = [c for c in home.get("changes", []) if c.get("metric_id") in vis]
        # Counted after filtering: a summary that still counted a withheld item would tell this
        # role there is work they cannot see.
        kept = {}
        for item in home["insights"]:
            kept[item.get("action_category")] = kept.get(item.get("action_category"), 0) + 1
        home["action_summary"] = [{**row, "count": kept.get(row.get("category"), 0)}
                                  for row in home.get("action_summary", [])
                                  if kept.get(row.get("category"))]

        # The grouped subjects are rebuilt against what this role kept, so a group cannot count a
        # finding the role may not see -- and a subject whose every finding was withheld does not
        # appear at all.
        visible_insights = {i.get("insight_id") for i in home["needs_attention"]}
        regrouped = []
        for group in home.get("attention_subjects", []):
            items = [i for i in group.get("items", [])
                     if i.get("insight_id") in visible_insights]
            if not items:
                continue
            regrouped.append({**group, "items": items, "finding_count": len(items),
                              "insight_ids": [i.get("insight_id") for i in items]})
        home["attention_subjects"] = regrouped
        return home

    # -- the owner's own decisions ----------------------------------------------------------------
    #
    # A recorded decision is a note about what the owner is doing. It is attached to the queue
    # item on the way out and never fed back into the engine: the definitions, the figures and
    # the trust posture are identical before and after one is written.

    def decision_log(self, role_id=ROLE_OWNER):
        home = self.owner_home(role_id)
        recorded = self.decisions.all()
        items = []
        for entry in home.get("decision_queue", []):
            key = entry.get("insight_id") or entry.get("title") or ""
            state = recorded.get(key) or {"status": "open", "status_label": "Open",
                                          "note": "", "decided_by": ""}
            items.append({**entry, "item_key": key, **state})
        return {"items": items, "statuses": [
            {"key": s, "label": STATUS_LABELS[s]} for s in STATUSES]}

    def record_decision(self, item_key, status, note="", decided_by="", role_id=ROLE_OWNER):
        self.authorizer.resolve(role_id)
        self.decisions.record(item_key, status, note=note, decided_by=decided_by)
        return self.decision_log(role_id)

    # -- export -----------------------------------------------------------------------------------

    def export_section(self, section_key, role_id=ROLE_OWNER, period="", compare="",
                       apartment=""):
        """The section the analyst is looking at, as rows.

        Built from the SAME authorized payload the page renders, after role filtering and after
        the gate. A measure with no permitted headline exports no headline: it exports its
        posture and its competing definitions, exactly as the screen shows them. Nothing here
        reaches past the presentation layer, so there is no path by which an export could carry
        a figure the screen may not.
        """
        payload = self.analytics_section(section_key, role_id, period=period, compare=compare,
                                         apartment=apartment)
        if not payload.get("available", False):
            return {"available": False, "reason": payload.get("reason", ""), "rows": []}

        rows = []
        for tile in payload.get("tiles", []):
            trust = (tile.get("trust") or {}).get("owner_label", "")
            # The caveat is written for the engine's audit trail and names records, files and
            # posture tokens. The owner's version of it is what the screen shows, and an export
            # of the screen carries the screen's words.
            note = _owner_note(tile.get("caveat", ""))
            title = op.owner_measure_name(tile.get("title", ""))
            series = tile.get("series_display") or {}
            if series:
                # A month-keyed measure exports one row per recorded month rather than a
                # truncated rendering of the whole dictionary in a single cell.
                for key in sorted(series):
                    # A month key is shown as the month; any other breakdown key is already the
                    # name of the thing it labels (a bed, an expense category) and is kept whole.
                    label = (key[:7] if _MONTH_KEY.match(str(key))
                             else _owner_label_for(key))
                    rows.append({"section": "Measures", "trust": trust, "note": note,
                                 "item": f"{title} — {label}", "value": series[key]})
            elif tile.get("headline_permitted") and tile.get("display_value"):
                rows.append({"section": "Measures", "item": title,
                             "value": tile.get("display_value", ""), "trust": trust,
                             "note": note})
            else:
                # No permitted headline: the competing definitions export, never a single
                # figure. Their labels are the registry's, so they go through the same owner
                # projection the screen uses rather than carrying database object names out.
                for index, definition in enumerate(tile.get("definitions", []) or [], start=1):
                    label = _export_definition_label(definition.get("label", ""), index)
                    rows.append({"section": "Measures", "trust": trust,
                                 "item": f"{title} — {label}",
                                 "value": _export_definition_value(
                                     definition.get("display_value", "")),
                                 "note": "One of several competing definitions."})
                if not (tile.get("definitions") or []):
                    rows.append({"section": "Measures", "item": title,
                                 "value": "", "trust": trust,
                                 "note": _owner_note(tile.get("unavailable_reason", ""))})

        for change in payload.get("changes", []):
            label = f"{change.get('previous_period','')} to {change.get('current_period','')}"
            rows.append({"section": "Movements", "item": change.get("title", ""),
                         "value": (f"{change.get('direction','')} {change.get('absolute_display','')}"
                                   .strip()),
                         "trust": (change.get("trust") or {}).get("owner_label", ""),
                         "note": (label + ". " + (change.get("unavailable_reason", "")
                                                  or change.get("component_note", ""))).strip()})
            for component in change.get("components", []) or []:
                rows.append({"section": "What drove the change",
                             "item": f"{change.get('title','')} — {component.get('label','')}",
                             "value": component.get("display_change", ""),
                             "trust": (change.get("trust") or {}).get("owner_label", ""),
                             "note": label})

        for insight in payload.get("insights", []):
            rows.append({"section": "Findings", "item": insight.get("category_label", ""),
                         "value": "", "trust": (insight.get("trust") or {}).get("owner_label", ""),
                         "note": " ".join(x for x in (insight.get("what_happened", ""),
                                                      insight.get("recommended_action", "")) if x)})

        for entry in self.decision_log(role_id)["items"]:
            rows.append({"section": "Decisions", "item": entry.get("title", ""),
                         "value": entry.get("status_label", ""), "trust": "",
                         "note": entry.get("decision", "")})

        return {"available": True, "section": payload.get("title", section_key),
                "as_of": payload.get("as_of", ""),
                "applied_filters": payload.get("applied_filters", {}), "rows": rows}

    def metrics(self, role_id=ROLE_OWNER):
        """Authorization filters WHICH metrics are listed. It never alters how one is gated."""
        visible = self.authorizer.filter_metrics(role_id)
        tiles = self._memo("tiles", lambda: {
            m: _plain(self.vb.tile(m).as_dict()) for m in self.registry.all_ids()})
        return {"role_id": role_id, "count": len(visible),
                "metrics": [tiles[m] for m in visible if m in tiles]}

    def metric_detail(self, metric_id, role_id=ROLE_OWNER):
        if not self.authorizer.may_see(role_id, metric_id):
            return {"metric_id": metric_id, "available": False,
                    "reason": f"Not visible to role {role_id!r}."}
        return _plain(self.vb.metric_detail(metric_id))

    def metric_action(self, metric_id, action, question="", role_id=ROLE_OWNER):
        """A metric card action, answered for the metric the card was built for.

        The id is the identity. Free-text questions still go to `ask()` and still resolve by
        name; this path exists so a card never has to describe its measure in a sentence and
        hope the resolver picks the same one.
        """
        if not self.authorizer.may_see(role_id, metric_id):
            return {"metric_id": metric_id, "action": action, "available": False,
                    "answer": f"Not visible to role {role_id!r}.",
                    "reason": f"Not visible to role {role_id!r}.",
                    "narrative_source": "deterministic", "narrative_note": "",
                    "guard_violations": []}

        # The deterministic answer, returned at once. The model is never called on this path: a
        # narrative, where one is eligible, is fetched separately by `metric_narrative` after this
        # answer is already on the owner's screen. The facts never leave the service.
        payload = _plain(self.vb.metric_action(metric_id, action, question))
        facts = payload.pop("narrative_facts", None)
        payload["narrative_source"] = "deterministic"
        # `guard_violations` keeps its meaning -- structured findings -- and stays empty on this
        # response: the findings are logged server-side. What the owner is told about a
        # narrative that was attempted and not used is `narrative_note`, and only that.
        payload["narrative_note"] = ""
        payload["guard_violations"] = []
        payload["narrative_pending"] = bool(
            self._narrative_eligible(metric_id, action, facts, payload)
            and self._narrative_active())
        return payload

    @staticmethod
    def _narrative_eligible(metric_id, action, facts, payload):
        """Switched on for this measure, AND today's result is one that may be narrated."""
        spec = narrative.spec_for(action, metric_id)
        if spec is None or not facts or not payload.get("available"):
            return False
        eligible, _reasons = narrative.eligibility_for(spec, facts)
        return eligible

    def metric_narrative(self, metric_id, action, question="", role_id=ROLE_OWNER):
        """The background half of a metric-card answer: a guarded Local LLM narrative, or nothing.

        Returns `narrative_source` "local_llm" with the narrative as `answer` when the model's
        wording passed the guard. Otherwise `narrative_source` "deterministic" and no answer: the
        deterministic answer already on the page stands, unchanged. `narrative_note` carries the
        owner-safe sentence only when a narrative was attempted and not used; the reason is logged.
        """
        result = {"metric_id": metric_id, "action": action, "narrative_source": "deterministic",
                  "narrative_note": "", "guard_violations": []}
        if not self.authorizer.may_see(role_id, metric_id):
            return result
        if narrative.spec_for(action, metric_id) is None or not self._narrative_active():
            return result         # not switched on, or disabled: the provider is never called

        # The same deterministic facts and answer the first response was built from. The engine is
        # deterministic over an immutable export, so they are the same facts, not new ones.
        payload = _plain(self.vb.metric_action(metric_id, action, question))
        facts = payload.pop("narrative_facts", None)
        if not self._narrative_eligible(metric_id, action, facts, payload):
            return result

        text, violations = self._metric_narrative(
            narrative.spec_for(action, metric_id), facts, payload.get("answer", ""))
        if text is None:
            _LOG.warning("metric narrative fallback for %s/%s: %s", metric_id, action,
                         " | ".join(str(v) for v in violations))
            self.obs.note_llm_fallback()
            result["narrative_note"] = narrative.FALLBACK_NOTE
            return result

        result["narrative_source"] = "local_llm"
        result["answer"] = text
        return result

    def _narrative_active(self):
        """Only an explicitly enabled HTTP adapter narrates. Offline mode is not a narrator."""
        config = self.provider_config
        return bool(config and config.explicitly_enabled and config.mode == MODE_HTTP)

    def _narrative_provider(self):
        """The configured provider. The narrative kind sets its own wait on it."""
        return build_provider(self.provider_config)

    def _metric_narrative(self, spec, facts, draft):
        """(narrative, ()) when the local model's wording passes the spec's guard, else (None, reasons).

        The provider call, the guard and the whole-output decision are `narrative.generate`'s; this
        supplies the configured provider and the measure names the guard checks against.
        """
        try:
            provider = self._narrative_provider()
        except LLMUnavailable as exc:
            return None, (f"local model unavailable: {exc}",)
        except Exception as exc:                     # a misconfigured adapter, never a 500
            return None, (f"local model failed: {type(exc).__name__}",)
        if hasattr(provider, "timeout"):
            provider.timeout = min(float(provider.timeout), float(spec.timeout_seconds))
        other_names = tuple(
            op.owner_measure_name(self.registry.get(m).display_name
                                  or self.registry.get(m).semantic_name)
            for m in self.registry.all_ids())
        return narrative.generate(spec, provider, facts, draft, other_measure_names=other_names)

    def conflict_view(self, metric_id, role_id=ROLE_OWNER):
        if not self.authorizer.may_see(role_id, metric_id):
            return {"metric_id": metric_id, "available": False,
                    "reason": f"Not visible to role {role_id!r}."}
        if metric_id not in self.registry:
            return {"metric_id": metric_id, "available": False,
                    "reason": f"{metric_id!r} is not a semantic metric. "
                              f"{NOT_DETERMINABLE_TEXT}"}
        lvl = self.gate.authorize(metric_id).effective_level
        if lvl not in ("SHOW_BOTH", "BLOCK"):
            return {"metric_id": metric_id, "available": False,
                    "reason": f"{metric_id} has one agreed definition ({lvl}); there is no "
                              f"conflict to display."}
        return _plain(self.vb.conflict_view(metric_id))

    def insights(self, role_id=ROLE_OWNER):
        home = self.owner_home(role_id)
        return {"count": len(home["insights"]), "insights": home["insights"]}

    def changes(self, role_id=ROLE_OWNER):
        home = self.owner_home(role_id)
        return {"count": len(home["changes"]), "changes": home["changes"]}

    def data_quality(self):
        return self._memo("data_quality", lambda: _plain(self.vb.data_quality_center()))

    # -- the semantic contract --------------------------------------------------------------------

    def metric_contract(self, metric_id, role_id=ROLE_OWNER):
        """What a measure MEANS: name, question, definition, grain, period, dimensions, posture,
        limitations, conflict behaviour, owner action, and the two usability answers."""
        if not self.authorizer.may_see(role_id, metric_id):
            return {"metric_id": metric_id, "available": False,
                    "reason": f"Not visible to role {role_id!r}."}
        return _plain(self.vb.metric_contract(metric_id))

    def metric_contracts(self, role_id=ROLE_OWNER):
        visible = set(self.authorizer.filter_metrics(role_id))
        rows = self._memo("metric_contracts", lambda: _plain(self.vb.metric_contracts()))
        return {"metrics": [c for c in rows if c.get("metric_id") in visible]}

    def unresolved_definitions(self, role_id=ROLE_OWNER):
        """Which measures still hold competing definitions, and which of those are waiting on a
        management decision. A listing only -- nothing here resolves anything."""
        visible = set(self.authorizer.filter_metrics(role_id))
        rows = self._memo("unresolved_definitions",
                          lambda: _plain(self.vb.unresolved_definitions()))
        kept = [r for r in rows if r.get("metric_id") in visible]
        return {"measures": kept,
                "decision_required": [r for r in kept if r.get("decision_required")]}

    # -- analytics sections (Phase 14) -----------------------------------------------------------

    def analytics_sections(self):
        """Directory of the four owner-facing analytics sections."""
        return self._memo("analytics_sections",
                          lambda: _plain(self.vb.analytics_sections()))

    def analytics_section(self, section_key, role_id=ROLE_OWNER, period="", compare="",
                          apartment=""):
        """One analytics section, filtered to what this role may see.

        Authorization removes metrics from the payload. It never changes a trust level, a
        value, or a limitation on a metric that survives the filter -- the same rule the
        dashboard and the metric detail already follow.

        `period`/`compare`/`apartment` are the analyst's own narrowing. They are part of the
        memo key, so a filtered payload is never served from an unfiltered cache entry.
        """
        self.authorizer.resolve(role_id)
        selection = {"period": period, "compare": compare, "apartment": apartment}
        key = "analytics:" + section_key + "|" + "|".join(
            str(selection[k] or "") for k in ("period", "compare", "apartment"))
        payload = dict(self._memo(
            key,
            lambda: _plain(self.vb.analytics_section(
                section_key, home=self._home_vm(), filters=selection))))
        if not payload.get("available", False):
            return payload

        vis = self._visible(role_id)
        payload["tiles"] = [t for t in payload.get("tiles", [])
                            if t.get("metric_id") in vis]
        payload["metric_count"] = len(payload["tiles"])
        payload["insights"] = [i for i in payload.get("insights", [])
                               if vis.issuperset(i.get("metric_ids") or ())]
        payload["changes"] = [c for c in payload.get("changes", [])
                              if c.get("metric_id") in vis]

        # Conflict and data-quality references are recomputed from the surviving tiles, so a
        # role never sees a reference pointing at a metric it cannot open.
        conflicts, dqs = set(), set()
        for t in payload["tiles"]:
            conflicts.update(t.get("conflict_ids") or ())
            dqs.update(t.get("dq_ids") or ())
        payload["conflict_ids"] = sorted(conflicts)
        payload["dq_ids"] = sorted(dqs)
        payload["trust_summary"] = _plain(vm._trust_breakdown(payload["tiles"]))
        return payload

    def roles(self):
        """The analyst workspaces. One card per lens -- `owner` is an identity presented through
        one of them, not a lens of its own, so it is not listed as a tenth workspace."""
        return {"roles": [self.authorizer.describe(r)
                          for r in self.authorizer.workspace_roles()]}

    def role_workspace(self, role_id):
        self.authorizer.resolve(role_id)
        target = self.authorizer.resolve(role_id).role_id
        return _plain(self.vb.role_workspace(target, home=self._home_vm()))

    def executive_report(self):
        summary = self.vb.summary_builder.build()
        return {"as_of": summary.generated_as_of,
                "text": render_summary(summary),
                "sections": list(summary.populated_sections()),
                "limitations": list(summary.limitations)}

    # -- conversation ------------------------------------------------------------------------------

    def ask(self, question, session: Session = None, conversation_id=None):
        """The natural-language entry point. Runs the SAME pipeline as every other surface."""
        session = session or Session(subject="anonymous", role_id=ROLE_OWNER)
        self.authorizer.resolve(session.role_id)

        conversation_id = conversation_id or str(uuid.uuid4())
        if not self.store.exists(conversation_id):
            self.store.create(conversation_id, session.subject, session.role_id)
        else:
            existing = self.store.get(conversation_id)
            if existing and existing["subject"] != session.subject:
                return {"conversation_id": conversation_id, "found": False,
                        "status": "unauthorized",
                        "answer": "No such conversation.",
                        "question": question, "trust_level": None, "metric_ids": [],
                        "headline_permitted": False, "limitations": [],
                        "evidence_chain": [], "guard_violations": []}

        ai = self._analyst()
        ai.llm.context.clear()
        self.store.restore_into(conversation_id, ai.llm.context)

        answer = ai.ask(question)
        vis = self._visible(session.role_id)
        if answer.metric_ids and not set(answer.metric_ids) <= vis:
            self.obs.inc("http.unauthorized_metric")
            return {
                "conversation_id": conversation_id,
                "question": question,
                "answer": "This question resolves to metrics that are not visible to this role.",
                "owner_intent": answer.owner_intent,
                "status": "unauthorized",
                "trust_level": answer.trust_level,
                "trust": tp.present(answer.trust_level).as_dict() if answer.trust_level else None,
                "metric_ids": [],
                "analyst_lenses": [],
                "headline_permitted": False,
                "limitations": list(answer.limitations),
                "evidence_chain": [],
                "guard_violations": [],
            }

        self.store.persist_from(conversation_id, ai.llm.context)
        self.store.append_turn(
            conversation_id, question,
            answer_text=answer.text, status=(answer.ask_result.status
                                             if answer.ask_result else answer.owner_intent),
            trust_level=answer.trust_level, metric_ids=answer.metric_ids,
            owner_intent=answer.owner_intent,
            # The structured interpretation, so the NEXT turn can resolve "Why?" against what
            # this one was about. Not the answer, and not its trust posture.
            request=(answer.ask_result.llm_request if answer.ask_result else None))

        chain = ai.explain(answer)
        # The technical chain stays exactly as it was, for developer and audit views. The owner
        # gets a projection of the SAME facts without metric IDs, filenames or module paths.
        # A capability-gap answer -- an unsupported forecast, a scenario -- carries no
        # Phase 4 result, and the panel came back empty: the owner opened "Why are you saying
        # this?" on the one kind of answer that is nothing BUT a reason, and was shown nothing.
        # The answer itself exposes the same fields the projection reads, so it stands in.
        source = answer.ask_result if answer.ask_result is not None else answer
        owner_why = {}
        try:
            owner_why = explainability.owner_projection(
                source, chain, registry=self.registry,
                change=getattr(source, "change", None),
                trust_level=answer.trust_level)
        except Exception:
            owner_why = {}
        if answer.trust_level:
            self.obs.note_trust(answer.trust_level)
        if answer.ask_result and answer.ask_result.guard_violations:
            self.obs.note_llm_fallback()
        if answer.ask_result and answer.ask_result.provider_error:
            self.obs.note_llm_fallback()
        return {
            "conversation_id": conversation_id,
            "question": question,
            "answer": answer.text,
            "owner_intent": answer.owner_intent,
            "status": (answer.ask_result.status if answer.ask_result else "WORKFLOW"),
            "trust_level": answer.trust_level,
            "trust": tp.present(answer.trust_level).as_dict() if answer.trust_level else None,
            "metric_ids": list(answer.metric_ids),
            "analyst_lenses": list(answer.routing.roles) if answer.routing else [],
            "headline_permitted": bool(
                answer.ask_result and answer.ask_result.plan
                and answer.ask_result.plan.headline_permitted),
            "limitations": list(answer.limitations),
            "evidence_chain": ([{"link": l.name, "content": l.content, "source": l.source,
                                 "present": l.present} for l in chain.links]
                               if chain else []),
            # Owner-readable projection of the same chain. The frontend shows THIS under
            # "Why are you saying this?"; `evidence_chain` remains for audit.
            "owner_explanation": owner_why,
            # Workflow answers carry their guard outcome on the answer itself; metric answers
            # carry it on the Phase 4 result. Both are reported, so the owner-facing "the
            # wording layer did not contribute" notice is accurate on every surface.
            "guard_violations": (list(answer.ask_result.guard_violations)
                                 if answer.ask_result
                                 else list(answer.guard_violations or ())),
            # True only when the wording layer was ACTUALLY asked and did not contribute. A
            # capability-gap answer is never sent to it -- the refusal is deterministic by
            # design -- so flagging one made the chat print "the wording layer did not
            # contribute to this answer", an explanation of an internal mechanism, above an
            # answer whose whole point was to be plain about a business limitation.
            "llm_fallback": bool(
                (answer.ask_result and (answer.ask_result.guard_violations
                                        or answer.ask_result.provider_error))
                or (answer.ask_result is None
                    and answer.owner_intent in ai_mod.WORKFLOW_INTENTS
                    and not answer.verbalized)),
        }

    def conversation(self, conversation_id, identity_subject=None):
        c = self.store.get(conversation_id)
        if c is None:
            return {"conversation_id": conversation_id, "found": False}
        if identity_subject is not None and c["subject"] != identity_subject:
            return {"conversation_id": conversation_id, "found": False}
        return {**_plain(c), "found": True}

    def close(self):
        self.store.close()


# --- FastAPI routing layer --------------------------------------------------------------------

def create_app(service: AnalyticsService = None, authenticator=None, rate_limiter=None):
    """A thin adapter. All behaviour lives in AnalyticsService, so the framework is swappable
    and the service is testable without HTTP."""
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field
    from starlette.middleware.base import BaseHTTPMiddleware

    svc = service or AnalyticsService()
    authenticator = authenticator or svc.authenticator
    limiter = rate_limiter or sec.RateLimiter()

    app = FastAPI(
        title="AI Business Analytics API",
        version=API_VERSION,
        description=(
            "Trust-gated business analytics. Every payload originates from the deterministic "
            "engine. No endpoint accepts a formula, filter expression, or query: the input "
            "surface carries identifiers only, so no client can ask the service to compute "
            "something the semantic layer does not already define. "
            "API routes require a Bearer identity; x-role is not authentication."),
    )

    origins = list(sec.cors_origins())
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )

    class _SecurityMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            rid = svc.obs.new_request_id(request.headers.get("x-request-id", ""))
            request.state.request_id = rid
            path = request.url.path
            key = request.client.host if request.client else "unknown"
            ident = None
            if path.startswith("/api/"):
                try:
                    ident = authenticator.authenticate(request.headers)
                    svc.authorizer.resolve(ident.role_id)
                    request.state.identity = ident
                    key = ident.subject
                except auth_mod.AuthenticationError:
                    svc.obs.inc("http.401")
                    resp = JSONResponse({"detail": "Authentication required."}, status_code=401)
                    for k, v in sec.security_headers(rid).items():
                        resp.headers[k] = v
                    return resp
                except AuthorizationError:
                    resp = JSONResponse({"detail": "Not authorized for this role."},
                                        status_code=403)
                    for k, v in sec.security_headers(rid).items():
                        resp.headers[k] = v
                    return resp
                if not limiter.allow(key):
                    svc.obs.inc("http.429")
                    resp = JSONResponse({"detail": "Rate limit exceeded."}, status_code=429)
                    for k, v in sec.security_headers(rid).items():
                        resp.headers[k] = v
                    return resp
            try:
                response = await call_next(request)
            except Exception as e:
                svc.obs.audit(request_id=rid, path=path, status=500,
                              outcome="error", error_type=type(e).__name__)
                response = JSONResponse({"detail": sec.sanitize_error(e)}, status_code=500)
            if path.startswith("/api/"):
                body = getattr(response, "body", b"") or b""
                try:
                    text = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else ""
                except Exception:
                    text = ""
                if text and sec.contains_secret_material(
                        text, extra_secrets=sec.collect_configured_secrets()):
                    svc.obs.inc("http.secret_redacted")
                    response = JSONResponse(
                        {"detail": "The request could not be completed."}, status_code=500)
            for k, v in sec.security_headers(rid).items():
                response.headers[k] = v
            if path.startswith("/api/"):
                response.headers["Cache-Control"] = "no-store"
            ident_fields = {}
            if ident is not None:
                ident_fields = {"subject": ident.subject, "role_id": ident.role_id}
            extra = getattr(request.state, "audit", None) or {}
            svc.obs.audit(request_id=rid, method=request.method, path=path,
                          status=getattr(response, "status_code", 0),
                          source_name=svc.source.descriptor().name,
                          source_status=svc.source.descriptor().status,
                          **ident_fields, **extra)
            return response

    app.add_middleware(_SecurityMiddleware)

    from fastapi.openapi.utils import get_openapi

    def _openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title, version=app.version, description=app.description, routes=app.routes)
        comps = schema.setdefault("components", {})
        comps.setdefault("securitySchemes", {})["BearerAuth"] = {
            "type": "http", "scheme": "bearer",
            "description": "Authenticated identity. Role is inside the token; x-role is ignored.",
        }
        for path, ops in schema.get("paths", {}).items():
            if not str(path).startswith("/api/"):
                continue
            for op in ops.values():
                if isinstance(op, dict):
                    op["security"] = [{"BearerAuth": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = _openapi

    class AskRequest(BaseModel):
        question: str = Field(..., min_length=1, max_length=sec.MAX_QUESTION_CHARS)
        conversation_id: str | None = None

    def _identity(request: Request) -> auth_mod.Identity:
        ident = getattr(request.state, "identity", None)
        if ident is None:
            raise HTTPException(status_code=401, detail="Authentication required.")
        return ident

    @app.get("/health")
    def health():
        return svc.health()

    @app.get("/api/trust")
    def trust(request: Request):
        _identity(request)
        return svc.trust_summary()

    @app.get("/api/llm/adapters")
    def llm_adapters(request: Request):
        _identity(request)
        return svc.llm_adapters()

    @app.get("/api/owner/home")
    def owner_home(request: Request):
        ident = _identity(request)
        return svc.owner_home(ident.role_id)

    @app.get("/api/analytics")
    def analytics_sections(request: Request):
        _identity(request)
        return svc.analytics_sections()

    @app.get("/api/analytics/{section}")
    def analytics_section(section: str, request: Request,
                          period: str = "", compare: str = "", apartment: str = ""):
        ident = _identity(request)
        return svc.analytics_section(section, ident.role_id, period=period,
                                     compare=compare, apartment=apartment)

    @app.get("/api/analytics/{section}/export")
    def analytics_export(section: str, request: Request,
                         period: str = "", compare: str = "", apartment: str = ""):
        ident = _identity(request)
        return svc.export_section(section, ident.role_id, period=period, compare=compare,
                                  apartment=apartment)

    @app.get("/api/decisions")
    def decisions(request: Request):
        ident = _identity(request)
        return svc.decision_log(ident.role_id)

    class DecisionRequest(BaseModel):
        item_key: str = Field(..., min_length=1, max_length=200)
        status: str = Field(..., min_length=1, max_length=40)
        note: str = Field("", max_length=2000)

    @app.post("/api/decisions")
    def record_decision(req: DecisionRequest, request: Request):
        ident = _identity(request)
        try:
            return svc.record_decision(req.item_key, req.status, note=req.note,
                                       decided_by=ident.subject, role_id=ident.role_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/metrics")
    def metrics(request: Request):
        ident = _identity(request)
        return svc.metrics(ident.role_id)

    @app.get("/api/metrics/{metric_id}")
    def metric_detail(metric_id: str, request: Request):
        ident = _identity(request)
        return svc.metric_detail(metric_id, ident.role_id)

    @app.get("/api/metrics/{metric_id}/action")
    def metric_action(metric_id: str, request: Request, action: str = "explain",
                      question: str = ""):
        ident = _identity(request)
        return svc.metric_action(metric_id, action, question, ident.role_id)

    @app.get("/api/metrics/{metric_id}/narrative")
    def metric_narrative(metric_id: str, request: Request, action: str = "why",
                         question: str = ""):
        # A plain (non-async) route: the framework runs it on a worker thread, so a slow local
        # model occupies that worker and never the event loop serving the rest of the dashboard.
        ident = _identity(request)
        return svc.metric_narrative(metric_id, action, question, ident.role_id)

    @app.get("/api/metrics/{metric_id}/conflict")
    def conflict(metric_id: str, request: Request):
        ident = _identity(request)
        return svc.conflict_view(metric_id, ident.role_id)

    @app.get("/api/contracts")
    def metric_contracts(request: Request):
        ident = _identity(request)
        return svc.metric_contracts(ident.role_id)

    @app.get("/api/contracts/unresolved")
    def unresolved_definitions(request: Request):
        ident = _identity(request)
        return svc.unresolved_definitions(ident.role_id)

    @app.get("/api/metrics/{metric_id}/contract")
    def metric_contract(metric_id: str, request: Request):
        ident = _identity(request)
        return svc.metric_contract(metric_id, ident.role_id)

    @app.get("/api/insights")
    def insights(request: Request):
        ident = _identity(request)
        return svc.insights(ident.role_id)

    @app.get("/api/changes")
    def changes(request: Request):
        ident = _identity(request)
        return svc.changes(ident.role_id)

    @app.get("/api/data-quality")
    def data_quality(request: Request):
        _identity(request)
        return svc.data_quality()

    @app.get("/api/roles")
    def roles(request: Request):
        _identity(request)
        return svc.roles()

    @app.get("/api/roles/{role_id}/workspace")
    def workspace(role_id: str, request: Request):
        ident = _identity(request)
        if ident.role_id not in (ROLE_OWNER, role_id):
            raise HTTPException(status_code=404, detail="No such workspace.")
        try:
            return svc.role_workspace(role_id)
        except AuthorizationError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/report/executive")
    def executive_report(request: Request):
        _identity(request)
        return svc.executive_report()

    @app.post("/api/ask")
    def ask(req: AskRequest, request: Request):
        ident = _identity(request)
        result = svc.ask(req.question, ident.session(), req.conversation_id)
        request.state.audit = {
            "metric_ids": list(result.get("metric_ids") or []),
            "intent": result.get("owner_intent"),
            "trust_level": result.get("trust_level"),
            "outcome": result.get("status"),
            "llm_fallback": bool(result.get("llm_fallback")),
            "guard_violations_count": len(result.get("guard_violations") or []),
        }
        return result

    @app.get("/api/conversations/{conversation_id}")
    def conversation(conversation_id: str, request: Request):
        ident = _identity(request)
        c = svc.conversation(conversation_id, ident.subject)
        if not c.get("found"):
            raise HTTPException(status_code=404, detail="No such conversation.")
        return c

    @app.get("/session", include_in_schema=False)
    def owner_session():
        """A bearer token for the owner's browser, where the deployment asked for one.

        Deliberately NOT under /api/, because a path that requires a token cannot be the way a
        browser obtains one. Everything else about the request path is unchanged: the same
        security headers, the same sanitisation, and every subsequent call still carries and
        verifies the token.

        Returns 404 unless AI_ANALYTICS_OWNER_OPEN=true AND a signing secret is configured, so a
        service that was not set up for an unlisted single-owner URL does not answer this at all.
        The secret is never in the response -- only a signed, expiring token minted from it.
        """
        token = auth_mod.owner_session_token()
        if not token:
            raise HTTPException(status_code=404, detail="Not found.")
        return {"token": token, "expires_in": auth_mod.TOKEN_TTL_SECONDS}

    frontend_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
    if os.path.isdir(frontend_dir):
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(os.path.join(frontend_dir, "index.html"))

    app.state.service = svc
    app.state.frontend_dir = frontend_dir
    app.state.authenticator = authenticator
    return app
