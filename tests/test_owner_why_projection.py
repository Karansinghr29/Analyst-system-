"""
test_owner_why_projection.py -- "Why are you saying this?" must be the owner's reason.

The evidence chain is the audit record and is correct as it stands: it names measure IDs,
source objects, specification sections and engine modules, because an auditor needs to retrace
exactly what ran. Shown to a business owner, that same record answers a question they did not
ask. These tests pin the projection of it -- same facts, business vocabulary, nothing that
identifies the implementation.

Three tests, one per trust posture, because the projection is keyed on the posture: a BLOCK is
explained by the conflict, a SAFE by the agreement, a SHOW_BOTH by the multiplicity.
"""
import re

import pytest

from engine import explainability as ex
from engine.llm_interface import LLMInterface


# Everything that identifies HOW the system is built rather than WHAT the measure means.
FORBIDDEN = {
    "measure/source handle": re.compile(
        r"\b(?:M|T|F|FN|H|D|DQ|C|INS)\.[A-Za-z0-9_.]+\b"),
    "file name": re.compile(r"\b[\w-]+\.(?:md|csv|py|json|sql|ya?ml)\b", re.I),
    "module path": re.compile(r"\b(?:engine|api|frontend|tests|scripts)[/.][\w/.]+", re.I),
    "database object": re.compile(
        r"\b(?:public\.[\w.]+|v_[a-z0-9_]+|vw_[a-z0-9_]+|get_[a-z0-9_]+)\b", re.I),
    "SQL": re.compile(r"\b(?:GROUP\s+BY|ORDER\s+BY|SELECT|WHERE|SUM\(|COUNT\(|JOIN)\b", re.I),
    "internal terminology": re.compile(
        r"\b(?:trust\s+gate|layer\s*[123]|semantic[_ ]metric[_ ]registry|planner|executor"
        r"|metric_id|execution_call|ai_handling|plan_type)\b", re.I),
    "raw dictionary": re.compile(r"[{\[]\s*['\"]?\w+['\"]?\s*[:,]"),
}


@pytest.fixture(scope="module")
def iface():
    return LLMInterface()


def why_text(iface, question):
    """The owner-facing explanation for one question, as the panel would render it."""
    result = iface.ask(question)
    iface.reset()
    projection = ex.owner_projection(result, registry=iface.registry,
                                     change=getattr(result, "change", None))
    rendered = ex.render_owner_projection(projection)
    assert rendered.strip(), f"{question!r} produced no owner explanation at all"
    return result, projection, rendered


def assert_owner_clean(rendered, question):
    for label, pattern in FORBIDDEN.items():
        found = pattern.search(rendered)
        assert not found, (
            f"{question!r} exposed {label} ({found.group(0)!r}) to the owner:\n{rendered}")


def test_block_profit_explanation_is_owner_facing(iface):
    """A BLOCK is explained by the conflict, and says whose decision resolves it."""
    question = "What was profit last month?"
    result, projection, rendered = why_text(iface, question)
    assert result.trust_level == "BLOCK"

    assert_owner_clean(rendered, question)
    low = rendered.lower()
    assert "blocked" in projection["heading"].lower()
    assert "profit" in low
    assert "do not agree" in low or "disagree" in low
    assert "decision" in low, "the owner is not told what would resolve it"


def test_safe_revenue_explanation_is_owner_facing(iface):
    """A SAFE answer explains WHY it can be relied on -- not how it was computed."""
    question = "How much revenue did we make?"
    result, projection, rendered = why_text(iface, question)
    assert result.trust_level == "SAFE"

    assert_owner_clean(rendered, question)
    low = rendered.lower()
    assert "trusted" in projection["heading"].lower()
    assert "one agreed definition" in low
    assert "checked against" in low


def test_show_both_tenant_dues_explanation_is_owner_facing(iface):
    """A SHOW_BOTH explains why several figures are shown and refuses to pick."""
    question = "How much do tenants owe?"
    result, projection, rendered = why_text(iface, question)
    assert result.trust_level == "SHOW_BOTH"

    assert_owner_clean(rendered, question)
    low = rendered.lower()
    assert "multiple figures" in projection["heading"].lower()
    assert "tenant dues" in low
    assert "business decision" in low
    assert "shown all of them" in low or "rather than selecting one" in low
