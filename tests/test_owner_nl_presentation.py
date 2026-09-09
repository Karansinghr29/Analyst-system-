"""
test_owner_nl_presentation.py -- the owner chat must read as business English, not engine output.

The subject here is ONLY the natural-language presentation layer. Every test below asserts one
of two things:

  * the owner is not shown engine internals -- raw dicts, metric IDs, DQ IDs, database object
    names, specification filenames, SQL;
  * the wording layer changed nothing that matters -- the same figures, the same trust posture,
    every competing definition, every caveat.

The second group is the important one. Making an answer readable is only worth doing if it
cannot also make it wrong, so each readability guarantee is paired with a correctness one.

A hostile verbalizer is used to attack the guard directly: the point is not that a small local
model happens to behave, but that a misbehaving one cannot reach the owner.
"""
import os
import re
import tempfile

import pytest

from engine import owner_presentation as op
from engine import answer_renderer
from engine.analyst_intelligence import AnalystIntelligence
from engine.llm_provider import LLMUnavailable
from engine.result import NOT_DETERMINABLE_TEXT
from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from api.service import AnalyticsService, create_app
from api import auth as auth_mod

from fastapi.testclient import TestClient


# --- what must never appear in owner prose ------------------------------------------------

METRIC_ID = re.compile(r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b")
DQ_ID = re.compile(r"\bDQ\.\d{3}\b")
CONFLICT_ID = re.compile(r"\bC\.\d{3}\b")
SPEC_FILE = re.compile(r"\b[\w.-]+\.(?:md|csv|py|json)\b", re.I)
DB_OBJECT = re.compile(r"\b(?:v_[a-z0-9_]+|vw_[a-z0-9_]+|get_[a-z0-9_]+)\b", re.I)
DICT_DUMP = re.compile(r"\{['\"]?\w+['\"]?\s*:")          # {'occupied': 168 ...
SQL = re.compile(r"\bselect\b[\s\S]{0,120}\bfrom\b", re.I)

OWNER_QUESTIONS = [
    "How is my business doing?",
    "What are my biggest risks?",
    "What changed?",
    "What should I focus on?",
    "Which numbers should I trust?",
    "How much revenue did we make?",
    "How much do tenants owe?",
    "What is our occupancy?",
    "What is our profit?",
]


@pytest.fixture(scope="module")
def client():
    """Offline deterministic provider: these tests are about the presentation layer, and must
    not depend on a model being installed."""
    svc = AnalyticsService(db_path=os.path.join(tempfile.mkdtemp(), "nl.db"),
                           authenticator=auth_mod.suite_authenticator())
    c = TestClient(create_app(svc, authenticator=auth_mod.suite_authenticator()))
    c.headers.update(auth_mod.bearer_headers())
    return c


@pytest.fixture(scope="module")
def answers(client):
    out = {}
    for q in OWNER_QUESTIONS:
        out[q] = client.post("/api/ask", json={"question": q}).json()
    return out


# --- no engine internals in owner prose ------------------------------------------------------

@pytest.mark.parametrize("question", OWNER_QUESTIONS)
def test_no_raw_dict_reaches_the_owner(answers, question):
    text = answers[question]["answer"] or ""
    assert not DICT_DUMP.search(text), f"a Python dict reached the owner:\n{text[:400]}"


@pytest.mark.parametrize("question", OWNER_QUESTIONS)
def test_no_metric_or_dq_id_reaches_the_owner(answers, question):
    text = answers[question]["answer"] or ""
    assert not METRIC_ID.search(text), f"a metric ID reached the owner:\n{text[:400]}"
    assert not DQ_ID.search(text), f"a DQ ID reached the owner:\n{text[:400]}"
    assert not CONFLICT_ID.search(text), f"a conflict ID reached the owner:\n{text[:400]}"


@pytest.mark.parametrize("question", OWNER_QUESTIONS)
def test_no_internal_file_or_object_name_reaches_the_owner(answers, question):
    text = answers[question]["answer"] or ""
    assert not SPEC_FILE.search(text), f"a spec filename reached the owner:\n{text[:400]}"
    assert not DB_OBJECT.search(text), f"a database object name reached the owner:\n{text[:400]}"
    assert not SQL.search(text), f"SQL reached the owner:\n{text[:400]}"


def test_the_specific_identifiers_named_in_the_brief_are_absent(answers):
    """M.AR.001A and DQ.016 were the examples given; assert them by name."""
    joined = "\n".join((a["answer"] or "") for a in answers.values())
    assert "M.AR.001A" not in joined
    assert "DQ.016" not in joined


@pytest.mark.parametrize("question", OWNER_QUESTIONS)
def test_currency_is_written_as_money(answers, question):
    """A bare 72705593.43 is engine output. The owner reads grouped digits."""
    text = answers[question]["answer"] or ""
    for bare in re.findall(r"(?<![\d,.₹])\d{6,}\.\d{2}\b", text):
        pytest.fail(f"ungrouped figure {bare!r} shown to the owner in {question!r}")


def test_a_change_is_not_described_with_a_double_negative(client):
    """"decreased by -221,734.74" reads as an increase."""
    text = client.post("/api/ask", json={"question": "What changed?"}).json()["answer"] or ""
    assert "decreased by -" not in text
    assert "increased by -" not in text
    assert not re.search(r"\(-\d", text), "a negative percentage sits beside a direction word"


def test_no_sentence_starts_with_an_orphaned_fragment(answers):
    """Stripping an identifier used to leave "'s monthly values are composite"."""
    for question, payload in answers.items():
        for line in (payload["answer"] or "").splitlines():
            body = line.lstrip("• ").strip()
            assert not body.startswith("'s "), f"orphaned possessive in {question!r}: {line!r}"
            assert not body.startswith("s "), f"orphaned fragment in {question!r}: {line!r}"


# --- the wording layer changed nothing that matters --------------------------------------------

def test_deterministic_values_are_unchanged(client):
    """The figure in the owner answer is the figure the engine computed."""
    from engine.execution import MetricExecutor
    executed = MetricExecutor().execute("M.REV.001")
    value = executed.results[0].value

    text = client.post("/api/ask",
                       json={"question": "How much revenue did we make?"}).json()["answer"] or ""
    figures = {f.replace(",", "") for f in re.findall(r"[\d,]+\.\d{2}", text)}
    assert f"{value:.2f}" in figures, (
        f"the engine computed {value}, which does not appear in the owner answer:\n{text[:400]}")


def test_block_stays_blocked(client):
    body = client.post("/api/ask", json={"question": "What is our profit?"}).json()
    if body["status"] != "BLOCKED":
        pytest.skip(f"profit did not resolve to BLOCKED (status {body['status']})")
    assert body["headline_permitted"] is False
    assert body["trust_level"] == "BLOCK"


def test_show_both_keeps_every_definition(client):
    body = client.post("/api/ask", json={"question": "What is our occupancy?"}).json()
    if body["trust_level"] != "SHOW_BOTH":
        pytest.skip(f"occupancy did not resolve to SHOW_BOTH ({body['trust_level']})")
    text = body["answer"] or ""
    assert body["headline_permitted"] is False
    labels = re.findall(r"\bDef ([A-Z])\b", text)
    assert len(set(labels)) >= 2, f"only {set(labels)} definitions survived:\n{text[:500]}"
    for winner in ("the real ", "the correct figure", "we should use", "best estimate"):
        assert winner not in text.lower(), f"a winner was picked ({winner!r})"


def test_definition_labels_stay_distinguishable():
    """Shortening a label for the owner must never make two definitions read alike -- that
    would collapse a SHOW_BOTH answer through the back door."""
    family = [
        "Tenant dues -- Def A: v_outstanding_receivables (reversals excluded)",
        "Tenant dues -- Def B: v_tenant_current_dues (reversals included)",
        "Tenant dues -- Def C: application tenant_allotments.balance_due",
    ]
    shortened = [op.owner_definition_label(x) for x in family]
    assert len(set(shortened)) == len(family), f"labels collapsed: {shortened}"
    assert all(s for s in shortened)


def test_not_determinable_keeps_the_exact_phrase(client, registry=None):
    registry = SemanticRegistry()
    gate = TrustGate(registry)
    nd = [m for m in registry.all_ids()
          if gate.authorize(m).effective_level == "NOT_DETERMINABLE"]
    assert nd, "no NOT_DETERMINABLE metric to exercise"
    detail = client.get(f"/api/metrics/{nd[0]}").json()
    assert NOT_DETERMINABLE_TEXT in detail["tile"]["unavailable_reason"]


def test_a_conflicted_kpi_does_not_repeat_its_own_label(client):
    """"Tenant dues -- Def A: ... . Tenant dues -- Def A: ..." was a stutter, not a briefing."""
    text = client.post("/api/ask",
                       json={"question": "How is my business doing?"}).json()["answer"] or ""
    for line in text.splitlines():
        head = line.split(":", 1)[0].strip("• ").strip()
        if len(head) > 6:
            assert line.count(head) <= 1, f"label repeated on one line: {line[:200]!r}"


# --- the guard, attacked directly ---------------------------------------------------------------

DRAFT = (
    "Executive takeaway\n"
    "This is the business picture from the records.\n"
    "\n"
    "Key numbers\n"
    "• Revenue (total, ledger-derived): ₹72,705,593.43\n"
    "• Collections by month decreased by ₹221,734.74 (5.88%).\n"
)


def test_guard_rejects_an_invented_number():
    v = answer_renderer.guard_workflow(
        "Revenue was ₹99,999,999.00 this year.", DRAFT)
    assert any("introduces the number" in x for x in v)


def test_guard_rejects_internal_identifiers():
    for bad, why in (("Revenue M.REV.001 was ₹72,705,593.43.", "metric ID"),
                     ("See DQ.016 for detail.", "data-quality ID"),
                     ("From v_outstanding_receivables.", "database object"),
                     ("Per conflicts.md.", "specification filename")):
        v = answer_renderer.guard_workflow(bad, DRAFT)
        assert v, f"guard accepted {why}: {bad!r}"


def test_guard_rejects_invented_materiality_and_cause():
    assert answer_renderer.guard_workflow(
        "Revenue of ₹72,705,593.43 is a significant improvement.", DRAFT)
    assert answer_renderer.guard_workflow(
        "Collections fell by ₹221,734.74 because of late payers.", DRAFT)


def test_guard_rejects_pii():
    assert answer_renderer.guard_workflow(
        "Call the tenant on their mobile number to chase it.", DRAFT)


def test_guard_accepts_a_faithful_restatement():
    good = ("Executive takeaway\nThe business picture from your records.\n\n"
            "Key numbers\nRevenue was ₹72,705,593.43. "
            "Collections by month decreased by ₹221,734.74 (5.88%).")
    assert answer_renderer.guard_workflow(good, DRAFT) == ()


def test_guard_keeps_the_not_determinable_sentence():
    draft = "Occupancy cannot be compared. " + NOT_DETERMINABLE_TEXT
    assert answer_renderer.guard_workflow("Occupancy cannot be compared.", draft)
    assert answer_renderer.guard_workflow(
        "Occupancy cannot be compared. " + NOT_DETERMINABLE_TEXT, draft) == ()


# --- the model is untrusted: failure and misbehaviour both fall back safely ----------------------

class _Dead:
    """A provider that is simply not there."""
    def complete(self, *a, **k):
        raise LLMUnavailable("simulated outage")


class _Hostile:
    """A provider that answers fluently and wrongly."""
    def complete(self, *a, **k):
        class R:
            text = ("Revenue was ₹99,999,999.00, a significant improvement caused by "
                    "higher rents. See M.REV.001 in conflicts.md.")
        return R()


@pytest.mark.parametrize("provider,label", [(_Dead(), "outage"), (_Hostile(), "hostile")])
def test_workflow_falls_back_to_the_deterministic_answer(provider, label):
    """When the model is absent or wrong, the owner gets the engine's own concise answer.

    The fallback is the CONDENSED deterministic answer -- the same short brief the model would
    have been asked to re-word -- not the full internal draft. The full draft is retained on
    `owner_draft` for the engine and debug layers.
    """
    ai = AnalystIntelligence(provider=provider, verbalize=True)
    answer = ai.ask("How is my business doing?")

    assert answer.owner_draft, "the full deterministic draft was not retained"
    assert answer.verbalized is False
    assert answer.text.strip(), f"{label}: the owner was left with nothing"
    assert answer.text != "Revenue was 99,999,999.00", f"{label}: a rejected wording was shown"
    assert "99,999,999" not in answer.text, f"{label}: a fabricated figure reached the owner"
    assert not METRIC_ID.search(answer.text)
    # The concise answer must be a genuine summary, not the full draft dumped verbatim.
    assert len(answer.text) < len(answer.owner_draft)
    if label == "hostile":
        assert answer.guard_violations, "the hostile wording passed the guard"


def test_a_workflow_answer_keeps_the_owner_sections():
    """The six-part shape is what makes a briefing readable; it comes from the deterministic
    draft, so it survives whether or not a model is available."""
    ai = AnalystIntelligence(provider=_Dead(), verbalize=True)
    text = ai.ask("How is my business doing?").text
    assert "Executive takeaway" in text
    assert "Key numbers" in text


def test_followup_still_works_after_a_workflow_answer(client):
    """"Why?" after a briefing must still resolve rather than restarting the conversation."""
    first = client.post("/api/ask", json={"question": "How is my business doing?"}).json()
    second = client.post("/api/ask", json={"question": "Why?",
                                           "conversation_id": first["conversation_id"]}).json()
    assert second["status"] != "unauthorized"
    assert (second["answer"] or "").strip(), "the follow-up produced nothing"
    assert not METRIC_ID.search(second["answer"] or "")


def test_followup_on_a_blocked_metric_stays_blocked(client):
    first = client.post("/api/ask", json={"question": "What is our profit?"}).json()
    if first["status"] != "BLOCKED":
        pytest.skip("profit did not resolve to BLOCKED")
    second = client.post("/api/ask", json={"question": "Why?",
                                           "conversation_id": first["conversation_id"]}).json()
    assert second["headline_permitted"] is False
    assert second["trust_level"] == first["trust_level"]


def test_the_engine_still_holds_the_full_evidence(client):
    """Internals leave the owner's prose but must remain available to the engine/debug layer."""
    body = client.post("/api/ask",
                       json={"question": "How much revenue did we make?"}).json()
    chain = body["evidence_chain"]
    assert chain, "the evidence chain was emptied along with the owner prose"
    joined = " ".join(f"{l['content']} {l['source']}" for l in chain)
    assert METRIC_ID.search(joined) or "M.REV" in joined, (
        "the evidence chain no longer names the measure it used")
