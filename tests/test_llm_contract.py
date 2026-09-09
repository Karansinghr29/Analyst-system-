"""
Phase 4: the structured contract between the LLM and the deterministic engine.

    "Validate this object before execution. If invalid: LLM output -> validation failure ->
     no execution -> repair/clarification. Never execute an invalid plan."

Everything a model returns is untrusted text. These tests exercise the contract against a
HOSTILE model, not merely a cooperative one -- a validator that only ever sees well-formed input
proves nothing.
"""
import json

import pytest

from engine import structured_output, prompt_contracts
from engine.structured_output import parse_and_validate, LLMPlanRequest
from engine.llm_provider import (DeterministicMockProvider, CallableProvider, LLMUnavailable,
                                 LLMProvider)
from engine.llm_interface import LLMInterface


def _valid_payload(**overrides):
    p = {
        "intent": ["lookup"], "concept": "revenue", "metric_ids": ["M.REV.001"],
        "dimensions": [], "filters": {}, "time_range": "", "comparison": "",
        "requested_output": "value", "explanation_requested": False,
        "recommendation_requested": False, "clarification_needed": False,
        "clarification_reason": "",
    }
    p.update(overrides)
    return json.dumps(p)


class TestContractAcceptsValidInput:
    def test_a_well_formed_request_validates(self, registry):
        out = parse_and_validate(_valid_payload(), registry)
        assert out.valid
        assert out.request.metric_ids == ("M.REV.001",)
        assert out.request.intent == ("lookup",)

    def test_json_wrapped_in_prose_is_still_found(self, registry):
        text = f"Sure, here is the plan:\n```json\n{_valid_payload()}\n```\nHope that helps."
        assert parse_and_validate(text, registry).valid

    def test_schema_and_validator_never_drift(self, registry):
        """The prompt advertises a vocabulary; the validator enforces one. If they disagree, a
        model can be told to emit a value that is then rejected."""
        assert prompt_contracts.verify_prompt_vocabulary(registry) == []


class TestContractRejectsInventedContent:
    """The LLM must not invent metrics, tables, columns, or definitions."""

    def test_invented_metric_id_is_rejected(self, registry):
        out = parse_and_validate(
            _valid_payload(metric_ids=["M.MARGIN.001"], concept=""), registry)
        assert not out.valid
        assert any("does not exist in semantic_metric_registry" in v for v in out.violations)

    def test_invented_metric_is_not_repairable(self, registry):
        """Re-prompting cannot make a nonexistent metric exist, so no repair is attempted."""
        out = parse_and_validate(
            _valid_payload(metric_ids=["M.MARGIN.001"], concept=""), registry)
        assert out.repairable is False

    def test_invented_concept_is_rejected(self, registry):
        out = parse_and_validate(
            _valid_payload(concept="margin_analysis", metric_ids=[]), registry)
        assert not out.valid
        assert any("not in the concept map" in v for v in out.violations)

    def test_invented_dimension_is_rejected(self, registry):
        out = parse_and_validate(_valid_payload(dimensions=["profit_centre"]), registry)
        assert not out.valid
        assert any("not catalogued in business_dimensions" in v for v in out.violations)

    def test_raw_column_as_a_filter_key_is_rejected(self, registry):
        out = parse_and_validate(
            _valid_payload(filters={"journal_lines.debit": "100"}), registry)
        assert not out.valid

    def test_concept_and_metric_ids_may_not_contradict(self, registry):
        """A model naming concept=revenue but metric_ids=[M.PROFIT.001] is silently
        reinterpreting the concept."""
        out = parse_and_validate(
            _valid_payload(concept="revenue", metric_ids=["M.PROFIT.001"]), registry)
        assert not out.valid
        assert any("silently reinterpret" in v for v in out.violations)

    def test_unknown_intent_is_rejected(self, registry):
        out = parse_and_validate(_valid_payload(intent=["freeform_advice"]), registry)
        assert not out.valid

    def test_extra_field_is_rejected(self, registry):
        """The contract is closed: an unlisted field is evidence of an undescribed action."""
        payload = json.loads(_valid_payload())
        payload["sql"] = "SELECT * FROM journal_lines"
        out = parse_and_validate(json.dumps(payload), registry)
        assert not out.valid
        assert any("unexpected field" in v for v in out.violations)


class TestContractRejectsInjection:
    """There is no channel for SQL, a table name, or a file path -- attempts to smuggle one
    through a free-text field are refused, not sanitised."""

    @pytest.mark.parametrize("payload", [
        {"time_range": "SELECT * FROM journal_lines"},
        {"comparison": "DROP TABLE receipts "},
        {"clarification_reason": "read tenants.csv directly"},
        {"time_range": "union select password from users"},
        {"comparison": "compare against tenant_transactions"},
    ])
    def test_query_fragments_are_refused(self, registry, payload):
        out = parse_and_validate(_valid_payload(**payload), registry)
        assert not out.valid
        assert any("query fragment" in v or "table" in v.lower() for v in out.violations)

    def test_oversized_free_text_is_refused(self, registry):
        out = parse_and_validate(_valid_payload(time_range="x" * 5000), registry)
        assert not out.valid

    def test_malformed_json_is_repairable_not_executable(self, registry):
        out = parse_and_validate("this is not json at all", registry)
        assert not out.valid
        assert out.repairable is True
        assert out.request is None

    def test_no_partially_valid_request_is_ever_returned(self, registry):
        """A caller holding a partially-valid object is one forgotten check from executing it."""
        out = parse_and_validate(_valid_payload(dimensions=["nonsense"]), registry)
        assert out.request is None


class TestInvalidPlansNeverExecute:
    """The single most important Phase 4 exit criterion."""

    def test_invented_metric_never_reaches_execution(self, registry):
        provider = DeterministicMockProvider(scripted=[
            _valid_payload(concept="", metric_ids=["M.FAKE.001"]),
            _valid_payload(concept="", metric_ids=["M.FAKE.001"]),
        ])
        iface = LLMInterface(provider=provider, registry=registry)
        result = iface.ask("give me the fake metric")
        assert result.executed is False
        assert result.answers == ()
        assert result.contract_violations

    def test_sql_injection_never_reaches_execution(self, registry):
        provider = DeterministicMockProvider(scripted=[
            _valid_payload(time_range="SELECT * FROM journal_lines"),
            _valid_payload(time_range="SELECT * FROM journal_lines"),
        ])
        iface = LLMInterface(provider=provider, registry=registry)
        result = iface.ask("revenue; select * from journal_lines")
        assert result.executed is False

    def test_garbage_output_yields_clarification_not_execution(self, registry):
        provider = DeterministicMockProvider(scripted=["nonsense", "still nonsense"])
        iface = LLMInterface(provider=provider, registry=registry)
        result = iface.ask("How much revenue did we make?")
        assert result.executed is False
        assert result.clarification is not None

    def test_one_bounded_repair_attempt_is_made(self, registry):
        """Malformed-but-repairable output gets exactly one retry -- then stops."""
        provider = DeterministicMockProvider(scripted=["not json", _valid_payload()])
        iface = LLMInterface(provider=provider, registry=registry)
        result = iface.ask("How much revenue did we make?")
        assert result.repair_attempted is True
        assert result.executed is True

    def test_repair_is_not_attempted_for_a_nonexistent_metric(self, registry):
        provider = DeterministicMockProvider(scripted=[
            _valid_payload(concept="", metric_ids=["M.FAKE.001"])])
        iface = LLMInterface(provider=provider, registry=registry)
        result = iface.ask("fake metric")
        assert result.repair_attempted is False
        assert result.executed is False


class TestProviderAbstraction:
    def test_a_custom_provider_satisfies_the_interface(self, registry):
        calls = []

        def fake(prompt, system, max_tokens, temperature):
            calls.append(prompt)
            if "VERBALIZE" in system:
                return prompt.split("ANSWER SKELETON", 1)[1].strip()
            return _valid_payload()

        iface = LLMInterface(provider=CallableProvider(fake, name="custom"), registry=registry)
        result = iface.ask("How much revenue did we make?")
        assert result.executed is True
        assert result.trust_level == "SAFE"
        assert calls

    def test_provider_failure_degrades_to_refusal_not_a_guess(self, registry):
        class Broken(LLMProvider):
            name = "broken"

            def complete(self, prompt, *, system="", max_tokens=1024, temperature=0.0):
                raise LLMUnavailable("no credentials")

        iface = LLMInterface(provider=Broken(), registry=registry)
        result = iface.ask("How much revenue did we make?")
        assert result.executed is False
        assert "unavailable" in result.text.lower()
        assert result.provider_error

    def test_non_string_provider_output_is_rejected(self, registry):
        prov = CallableProvider(lambda **kw: {"not": "a string"}, name="bad")
        iface = LLMInterface(provider=prov, registry=registry)
        result = iface.ask("How much revenue did we make?")
        assert result.executed is False

    def test_default_provider_is_offline(self):
        """No test or script may accidentally require network access or spend credentials."""
        from engine.llm_provider import default_provider
        assert isinstance(default_provider(), DeterministicMockProvider)

    def test_swapping_providers_changes_no_engine_component(self, registry):
        """The same question through two different providers must produce the same trust
        posture, metric set, and values -- the provider governs language, never analytics."""
        a = LLMInterface(provider=DeterministicMockProvider(), registry=registry)
        b = LLMInterface(provider=CallableProvider(
            lambda prompt, system, max_tokens, temperature:
                prompt.split("ANSWER SKELETON", 1)[1].strip() if "VERBALIZE" in system
                else _valid_payload(), name="other"), registry=registry)
        ra = a.ask("How much revenue did we make?")
        rb = b.ask("How much revenue did we make?")
        assert ra.trust_level == rb.trust_level
        assert ra.metric_ids == rb.metric_ids
        assert (ra.answers[0].headline == rb.answers[0].headline)
