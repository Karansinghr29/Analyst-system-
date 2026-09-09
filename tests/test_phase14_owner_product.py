"""
test_phase14_owner_product.py -- the owner-facing product surfaces added in Phase 14.

Three things are under test, and the third is the one that matters most:

  1. The analytics sections serve real, evidence-backed content for all four domains.
  2. Conversation follow-ups ("Why?", "Explain this") resolve against the previous turn
     ACROSS an HTTP boundary, which is where they previously could not.
  3. Neither of the above weakened a trust guarantee. A follow-up that inherits a BLOCK metric
     must still be BLOCKED; an analytics tile must carry the gate's posture and no headline it
     is not permitted; capability disclosure must state its limitations rather than omit them.

The offline deterministic provider is used throughout, so these run without a model.
"""
import os
import tempfile

import pytest

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.view_models import ViewModelBuilder
from engine.capability_disclosure import (CapabilityDisclosure, SECTIONS, SECTION_SPEC,
                                          SECTION_RISK, SECTION_INSIGHTS)
from engine.conversation_context import ConversationContext, Turn
from engine.structured_output import LLMPlanRequest
from api.service import AnalyticsService, create_app
from api import auth as auth_mod
from api.conversation_store import ConversationStore

from fastapi.testclient import TestClient


# --- fixtures -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registry():
    return SemanticRegistry()


@pytest.fixture(scope="module")
def builder(registry):
    return ViewModelBuilder(registry=registry)


@pytest.fixture(scope="module")
def client():
    svc = AnalyticsService(db_path=os.path.join(tempfile.mkdtemp(), "p14.db"),
                           authenticator=auth_mod.suite_authenticator())
    c = TestClient(create_app(svc, authenticator=auth_mod.suite_authenticator()))
    c.headers.update(auth_mod.bearer_headers())
    return c


# --- capability disclosure ------------------------------------------------------------------

def test_every_section_declares_its_capabilities():
    disc = CapabilityDisclosure()
    for key in SECTIONS:
        caps = disc.for_section(key)
        assert caps["supported"], f"{key} claims no analysis at all"


def test_unsupported_analyses_are_disclosed_not_omitted():
    """The specifications decline to fix a materiality threshold, an anomaly bound and a
    statistical method. Those analyses must be NAMED as unavailable, with the reason."""
    disc = CapabilityDisclosure()
    caps = disc.for_section(SECTION_INSIGHTS)
    limited = list(caps["partial"]) + list(caps["unsupported"])
    assert limited, "no analysis is declared limited; the known gaps have been papered over"
    for item in limited:
        assert item["limitation"], (
            f"{item['capability_id']} is limited but states no reason; an owner cannot tell "
            f"an unsupported analysis from an overlooked one")


def test_capability_counts_match_the_registry():
    disc = CapabilityDisclosure()
    summary = disc.summary()
    assert summary["total"] == len(disc.rows)
    assert summary["by_status"].get("IMPLEMENTED", 0) > 0


# --- analytics sections ---------------------------------------------------------------------

def test_all_four_sections_are_available(builder):
    home = builder.owner_home()
    for key in SECTIONS:
        payload = builder.analytics_section(key, home=home)
        assert payload["available"] is True, key
        assert payload["title"] == SECTION_SPEC[key][0]


def test_domain_sections_carry_their_own_metrics(builder, registry):
    """A section shows the metrics of its own domain -- not a hand-picked subset, and not
    another domain's."""
    home = builder.owner_home()
    for key in SECTIONS:
        domain = SECTION_SPEC[key][1]
        if domain is None:
            continue
        payload = builder.analytics_section(key, home=home)
        assert payload["tiles"], f"{key} shows no measures"
        for tile in payload["tiles"]:
            assert registry.get(tile["metric_id"]).domain == domain


def test_section_tiles_carry_the_gate_posture(builder, registry):
    """Trust on an analytics tile is the gate's verdict, never a section-local decision."""
    gate = TrustGate(registry)
    home = builder.owner_home()
    for key in SECTIONS:
        payload = builder.analytics_section(key, home=home)
        for tile in payload["tiles"]:
            expected = gate.authorize(tile["metric_id"]).effective_level
            assert tile["trust"]["trust_level"] == expected, tile["metric_id"]


def test_no_analytics_tile_leaks_a_forbidden_headline(builder):
    """The load-bearing guarantee, re-asserted on the new surface: a tile that may not show a
    headline carries no value to show."""
    home = builder.owner_home()
    for key in SECTIONS:
        payload = builder.analytics_section(key, home=home)
        for tile in payload["tiles"]:
            if not tile["headline_permitted"]:
                assert tile["value"] is None, tile["metric_id"]
                assert not tile["display_value"], tile["metric_id"]


def test_show_both_tiles_keep_every_definition(builder):
    """A conflicted measure presents all of its definitions on the analytics surface too --
    collapsing to one would pick a winner the evidence does not."""
    home = builder.owner_home()
    seen = 0
    for key in SECTIONS:
        payload = builder.analytics_section(key, home=home)
        for tile in payload["tiles"]:
            if tile["headline_permitted"] or not tile["definitions"]:
                continue
            assert len(tile["definitions"]) >= 2, tile["metric_id"]
            seen += 1
    assert seen > 0, "no multi-definition tile was exercised"


def test_risk_section_carries_the_data_quality_findings(builder):
    payload = builder.analytics_section(SECTION_RISK)
    assert "data_quality" in payload
    assert payload["data_quality"]["total"] > 0


def test_insights_section_carries_decision_support(builder):
    payload = builder.analytics_section(SECTION_INSIGHTS)
    assert "decision_queue" in payload
    assert "recommended_actions" in payload


def test_unknown_section_is_refused_not_invented(builder):
    payload = builder.analytics_section("marketing")
    assert payload["available"] is False
    assert "marketing" in payload["reason"]


# --- API surface ------------------------------------------------------------------------------

def test_analytics_endpoints_serve_all_sections(client):
    directory = client.get("/api/analytics").json()
    keys = [s["section"] for s in directory["sections"]]
    assert keys == list(SECTIONS)
    for key in keys:
        r = client.get("/api/analytics/" + key)
        assert r.status_code == 200
        assert r.json()["available"] is True


def test_analytics_requires_authentication():
    svc = AnalyticsService(db_path=os.path.join(tempfile.mkdtemp(), "p14a.db"),
                           authenticator=auth_mod.suite_authenticator())
    anon = TestClient(create_app(svc, authenticator=auth_mod.suite_authenticator()))
    assert anon.get("/api/analytics").status_code == 401
    assert anon.get("/api/analytics/financial").status_code == 401


def test_analytics_section_matches_the_dashboard(client):
    """The dashboard and the analytics section must not be two analytics paths. Where they
    show the same measure, they must show the same posture and the same rendered value."""
    home = client.get("/api/owner/home").json()
    by_id = {t["metric_id"]: t
             for t in home["business_health"] + home["operations"] + home["risks"]}
    checked = 0
    for key in SECTIONS:
        payload = client.get("/api/analytics/" + key).json()
        for tile in payload.get("tiles", []):
            other = by_id.get(tile["metric_id"])
            if other is None:
                continue
            assert tile["trust"]["trust_level"] == other["trust"]["trust_level"]
            assert tile["headline_permitted"] == other["headline_permitted"]
            assert tile["display_value"] == other["display_value"]
            checked += 1
    assert checked > 0, "no overlapping measure was compared"


# --- conversation follow-ups -------------------------------------------------------------------

def test_store_round_trips_the_structured_request():
    """The follow-up mechanism depends on the previous turn's INTERPRETATION surviving a
    restart. The answer deliberately does not."""
    store = ConversationStore(os.path.join(tempfile.mkdtemp(), "turns.db"))
    store.create("c1", "owner", "owner")
    request = LLMPlanRequest(intent=("lookup",), concept="revenue",
                             metric_ids=("M.REV.001",), time_range="2026-07")
    store.append_turn("c1", "How much revenue?", answer_text="72,705,593.43",
                      trust_level="SAFE", metric_ids=("M.REV.001",), request=request)

    restored = store.turns("c1")[0]
    assert restored.request is not None
    assert restored.request.concept == "revenue"
    assert restored.request.metric_ids == ("M.REV.001",)
    assert restored.request.time_range == "2026-07"
    store.close()


def test_restore_carries_the_question_but_not_the_answer():
    """Restoring a past ANSWER could re-serve a stale trust posture. Restoring the past
    QUESTION cannot: the follow-up is re-executed from scratch."""
    store = ConversationStore(os.path.join(tempfile.mkdtemp(), "turns2.db"))
    store.create("c2", "owner", "owner")
    store.append_turn("c2", "How much revenue?", answer_text="a stale figure",
                      trust_level="SAFE", metric_ids=("M.REV.001",),
                      request=LLMPlanRequest(intent=("lookup",), concept="revenue",
                                             metric_ids=("M.REV.001",)))

    ctx = ConversationContext()
    store.restore_into("c2", ctx)
    assert len(ctx.turns) == 1
    assert ctx.last.question == "How much revenue?"
    assert ctx.last.request.concept == "revenue"
    assert ctx.last.answer is None, "a past answer was restored and could be re-served"
    assert ctx.last.trust_level == "", "a past trust posture was restored"
    store.close()


def test_migration_adds_the_column_to_an_existing_database():
    """An installation created before Phase 14 must keep working and gain the column."""
    import sqlite3
    path = os.path.join(tempfile.mkdtemp(), "old.db")
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE conversations (conversation_id TEXT PRIMARY KEY, subject TEXT NOT NULL,
            role_id TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE turns (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
            turn_index INTEGER NOT NULL, question TEXT NOT NULL, answer_text TEXT, status TEXT,
            trust_level TEXT, metric_ids TEXT, owner_intent TEXT, created_at REAL NOT NULL);
    """)
    old.commit()
    old.close()

    store = ConversationStore(path)
    cols = {r["name"] for r in store._conn.execute("PRAGMA table_info(turns)")}
    assert "request_json" in cols
    store.create("c3", "owner", "owner")
    store.append_turn("c3", "q", request=LLMPlanRequest(intent=("lookup",), concept="revenue"))
    assert store.turns("c3")[0].request.concept == "revenue"
    store.close()


@pytest.mark.parametrize("question", ["Why?", "Why.", "Explain this.", "Explain that",
                                      "Tell me more", "What about June?"])
def test_followup_phrasings_are_recognised(question):
    assert ConversationContext.looks_like_followup(question) is True


@pytest.mark.parametrize("question", ["How much revenue did we make?", "What is our occupancy?",
                                      "Show me financial issues.", "What are the biggest risks?"])
def test_fresh_questions_are_not_treated_as_followups(question):
    """A follow-up marker that fired on an ordinary question would let a previous subject leak
    into an unrelated one."""
    assert ConversationContext.looks_like_followup(question) is False


def test_followup_seed_requires_a_previous_subject():
    """Without a prior turn to refer to, the honest answer to "Why?" is still to ask."""
    ctx = ConversationContext()
    assert ctx.followup_seed("Why?") is None

    ctx.record(Turn(question="hello", request=LLMPlanRequest(intent=("meta",))))
    assert ctx.followup_seed("Why?") is None, "a turn with no subject was treated as one"

    ctx.record(Turn(question="How much revenue?",
                    request=LLMPlanRequest(intent=("lookup",), concept="revenue",
                                           metric_ids=("M.REV.001",))))
    seed = ctx.followup_seed("Why?")
    assert seed is not None
    assert seed.concept == "", "the seed pre-filled a concept instead of letting resolve() do it"
    assert seed.metric_ids == ()


def test_followup_seed_ignores_a_fresh_question():
    ctx = ConversationContext()
    ctx.record(Turn(question="How much revenue?",
                    request=LLMPlanRequest(intent=("lookup",), concept="revenue",
                                           metric_ids=("M.REV.001",))))
    assert ctx.followup_seed("What is our occupancy?") is None


def test_seeded_followup_inherits_through_the_normal_path():
    """The seed carries nothing; `resolve()` supplies the subject through the same additive
    inheritance every other follow-up uses."""
    ctx = ConversationContext()
    ctx.record(Turn(question="What is our profit?",
                    request=LLMPlanRequest(intent=("lookup",), concept="profit",
                                           metric_ids=("M.PROFIT.001",))))
    seed = ctx.followup_seed("Why?")
    resolved, inherited = ctx.resolve(seed, "Why?")
    assert resolved.concept == "profit"
    assert resolved.metric_ids == ("M.PROFIT.001",)
    assert "driver" in resolved.intent
    assert "concept" in inherited


def test_followup_over_http_keeps_the_blocked_posture(client):
    """The regression that matters. A follow-up inherits the SUBJECT, never a permission: a
    "Why?" about a BLOCKED measure stays blocked and states no figure."""
    first = client.post("/api/ask", json={"question": "What is our profit?"}).json()
    if first["status"] != "BLOCKED":
        pytest.skip(f"profit did not resolve to BLOCKED (status {first['status']})")

    second = client.post("/api/ask", json={"question": "Why?",
                                           "conversation_id": first["conversation_id"]}).json()
    assert second["headline_permitted"] is False
    assert second["trust_level"] == first["trust_level"]
    assert second["metric_ids"] == first["metric_ids"], "the follow-up lost its subject"


# --- payload memoisation ------------------------------------------------------------------------
#
# Caching an analytics payload is safe because the bound evidence is an immutable export.
# Caching an AUTHORIZED payload would not be. These tests pin that distinction.

@pytest.fixture(scope="module")
def service():
    return AnalyticsService(db_path=os.path.join(tempfile.mkdtemp(), "p14c.db"),
                            authenticator=auth_mod.suite_authenticator())


def test_memoised_payload_is_not_corrupted_by_role_filtering(service):
    """Filtering happens on a copy. Serving a narrow role must not shrink what a broad role
    sees on the next request."""
    roles = list(service.authorizer.known_roles())
    first = {r: len(service.owner_home(r)["business_health"]) for r in roles}
    second = {r: len(service.owner_home(r)["business_health"]) for r in roles}
    assert first == second


def test_authorization_is_applied_after_the_cache(service):
    """A restricted role must not inherit visibility from a broader role that was served
    first. This is the failure the cache could plausibly introduce, so it is tested directly."""
    broad = {m["metric_id"] for m in service.metrics("owner")["metrics"]}
    narrow = {m["metric_id"] for m in service.metrics("risk_dq_analyst")["metrics"]}
    assert narrow < broad, "a restricted role saw everything the owner sees"
    assert narrow == {m["metric_id"] for m in service.metrics("risk_dq_analyst")["metrics"]}


def test_analytics_sections_are_filtered_per_role(service):
    ops_only = service.analytics_section("financial", "operations_analyst")
    assert ops_only["metric_count"] == 0, "an operations lens was served financial measures"
    fin = service.analytics_section("financial", "financial_analyst")
    assert fin["metric_count"] > 0


def test_cache_is_rekeyed_when_the_source_changes(service):
    """The cache key is the bound source's own descriptor, so the eventual read-only Supabase
    activation discards every payload computed from the export rather than serving it on."""
    service._cache["__source__"] = ("some-other-source", "live", "TRUSTED", "2027-01-01")
    service.owner_home("owner")
    assert service._cache["__source__"] == service._source_fingerprint()


def test_warm_cache_builds_every_owner_surface(service):
    service.invalidate_cache()
    built = service.warm_cache()
    for key in ("owner_home", "tiles", "data_quality", "analytics_sections"):
        assert key in built
    for key in SECTIONS:
        assert "analytics:" + key in built


# --- the seed must never answer a different question than the one asked -------------------------

@pytest.mark.parametrize("question", ["Explain collections.", "What about maintenance?",
                                      "Why did occupancy fall?"])
def test_seed_refuses_a_followup_that_names_its_own_subject(question):
    """"Explain collections" reads as a follow-up by phrasing but says what it is about.
    Seeding it from the previous turn would answer a different question than the one asked --
    the exact failure the trust model exists to prevent. Clarification is the honest response."""
    ctx = ConversationContext()
    ctx.record(Turn(question="How much revenue?",
                    request=LLMPlanRequest(intent=("lookup",), concept="revenue",
                                           metric_ids=("M.REV.001",))))
    assert ctx.followup_seed(question) is None


@pytest.mark.parametrize("question", ["Why?", "Why.", "Explain this.", "Tell me more"])
def test_seed_accepts_a_bare_reference(question):
    ctx = ConversationContext()
    ctx.record(Turn(question="How much revenue?",
                    request=LLMPlanRequest(intent=("lookup",), concept="revenue",
                                           metric_ids=("M.REV.001",))))
    assert ctx.followup_seed(question) is not None


# --- every question the UI offers must actually be answerable ------------------------------------
#
# Shipping a suggestion chip that dead-ends trains the owner to distrust the buttons. These pin
# the routing for every phrase the dashboard and the chat present as a one-click question.

from engine.analyst_intelligence import classify_owner_intent

UI_QUESTIONS = {
    # chat suggestions
    "How is my business doing?": "briefing",
    "What changed this month?": "what_changed",
    "What should I focus on?": "what_to_do",
    "What are my biggest risks?": "what_to_do",
    "Which numbers should I trust?": "what_to_trust",
    # follow-up chips
    "What changed?": "what_changed",
    "What should I do?": "what_to_do",
    "Which area should I look at first?": "what_to_do",
    # dashboard entry points
    "How is the business doing?": "briefing",
    "What are our biggest business risks?": "what_to_do",
    "What should I do?": "what_to_do",
}


@pytest.mark.parametrize("question,expected", sorted(UI_QUESTIONS.items()))
def test_ui_questions_route_deterministically(question, expected):
    """These reach a deterministic workflow, so they answer whether or not a language model is
    reachable. A regression here would leave the owner's own dashboard buttons broken during an
    outage."""
    assert classify_owner_intent(question) == expected


@pytest.mark.parametrize("question", sorted(UI_QUESTIONS))
def test_ui_questions_answer_without_a_headline_they_may_not_give(client, question):
    r = client.post("/api/ask", json={"question": question})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "WORKFLOW", f"{question} fell through to a metric lookup"
    assert body["headline_permitted"] is False
