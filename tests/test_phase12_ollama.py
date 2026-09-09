"""
Phase 12: local Ollama adapter. Offline tests — no Ollama daemon required.

The live optional test is skipped unless AI_ANALYTICS_OLLAMA_LIVE_TEST=true.
"""
import json
import os
import urllib.error
import urllib.request

import pytest

from engine.llm_provider import (DeterministicMockProvider, CallableProvider, LLMUnavailable,
                                 OpenAICompatibleProvider, assert_loopback_endpoint,
                                 _RefuseRedirects, default_provider)
from engine.llm_interface import LLMInterface
from engine.gate import TrustGate
from engine.result import NOT_DETERMINABLE_TEXT
from engine import structured_output
from api import provider_config as pc
from api.provider_config import ProviderConfig, MODE_HTTP, MODE_OFFLINE


OLLAMA_LOOPBACK = "http://127.0.0.1:11434/v1"


def _enable_ollama(monkeypatch, url=OLLAMA_LOOPBACK, model="llama3.2", key="ollama"):
    monkeypatch.setenv(pc.ENV_ENABLE, "true")
    monkeypatch.setenv(pc.ENV_MODE, MODE_HTTP)
    monkeypatch.setenv(pc.ENV_ADAPTER, "ollama")
    if url is None:
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("OLLAMA_BASE_URL", url)
    if model is None:
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    else:
        monkeypatch.setenv("OLLAMA_MODEL", model)
    if key is None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OLLAMA_API_KEY", key)


def _hostile(registry, verbalize_fn, extract_json=None):
    def fn(prompt, system, max_tokens, temperature):
        if "VERBALIZE" in system or "VERBALIZE" in prompt:
            return verbalize_fn(prompt)
        if extract_json is not None:
            return extract_json
        return DeterministicMockProvider()._extract(prompt)
    return LLMInterface(provider=CallableProvider(fn, name="hostile-p12"),
                        registry=registry)


class TestOllamaOptIn:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv(pc.ENV_ENABLE, raising=False)
        monkeypatch.setenv("OLLAMA_BASE_URL", OLLAMA_LOOPBACK)
        monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
        monkeypatch.setenv("OLLAMA_API_KEY", "ollama")
        cfg = pc.config_from_env()
        assert cfg.mode == MODE_OFFLINE
        assert cfg.explicitly_enabled is False
        assert isinstance(pc.build_provider(cfg), DeterministicMockProvider)

    def test_enable_must_be_exact_true(self, monkeypatch):
        monkeypatch.setenv(pc.ENV_ENABLE, "True")  # not the exact token
        monkeypatch.setenv(pc.ENV_MODE, MODE_HTTP)
        monkeypatch.setenv(pc.ENV_ADAPTER, "ollama")
        cfg = pc.config_from_env()
        assert cfg.explicitly_enabled is False
        assert isinstance(pc.build_provider(cfg), DeterministicMockProvider)

    def test_running_daemon_env_does_not_enable_without_flag(self, monkeypatch):
        monkeypatch.delenv(pc.ENV_ENABLE, raising=False)
        for a in pc.available_adapters():
            if a["name"] == "ollama":
                assert a["enabled"] is False


class TestOllamaLoopbackPin:
    def test_loopback_url_constructs_existing_provider(self, monkeypatch):
        _enable_ollama(monkeypatch)
        cfg = pc.config_from_env()
        p = pc.build_provider(cfg)
        assert isinstance(p, OpenAICompatibleProvider)
        assert p.name == "ollama"
        assert p.loopback_only is True
        assert p.model == "llama3.2"
        d = cfg.describe()
        assert d["destination"] == pc.DESTINATION_LOCAL_LOOPBACK
        assert d["local_loopback"] is True
        assert d["network_access"] is False
        assert d["status"] == "LOCAL_LOOPBACK"
        assert "stay on this machine" in (d["note"] or "")

    def test_localhost_is_allowed(self, monkeypatch):
        _enable_ollama(monkeypatch, url="http://localhost:11434/v1")
        p = pc.build_provider(pc.config_from_env())
        assert p.loopback_only is True

    def test_ipv6_loopback_is_allowed(self, monkeypatch):
        _enable_ollama(monkeypatch, url="http://[::1]:11434/v1")
        p = pc.build_provider(pc.config_from_env())
        assert p.loopback_only is True

    def test_non_loopback_is_rejected(self, monkeypatch):
        _enable_ollama(monkeypatch, url="http://192.168.1.10:11434/v1")
        with pytest.raises(LLMUnavailable, match="loopback"):
            pc.build_provider(pc.config_from_env())

    def test_openai_public_endpoint_is_rejected(self, monkeypatch):
        _enable_ollama(monkeypatch, url="https://api.openai.com/v1")
        with pytest.raises(LLMUnavailable):
            pc.build_provider(pc.config_from_env())

    def test_groq_public_endpoint_is_rejected(self, monkeypatch):
        _enable_ollama(monkeypatch, url="https://api.groq.com/openai/v1")
        with pytest.raises(LLMUnavailable):
            pc.build_provider(pc.config_from_env())

    def test_redirect_to_non_loopback_is_rejected(self):
        handler = _RefuseRedirects()
        req = urllib.request.Request("http://127.0.0.1:11434/v1/chat/completions")
        with pytest.raises(urllib.error.HTTPError) as ei:
            handler.redirect_request(
                req, None, 302, "Found", {}, "https://api.openai.com/v1/chat/completions")
        assert "redirect" in str(ei.value).lower() or ei.value.code == 302

    def test_missing_model_is_rejected(self, monkeypatch):
        _enable_ollama(monkeypatch, model=None)
        with pytest.raises(LLMUnavailable, match="OLLAMA_MODEL"):
            pc.build_provider(pc.config_from_env())

    def test_missing_base_url_is_rejected(self, monkeypatch):
        _enable_ollama(monkeypatch, url=None)
        with pytest.raises(LLMUnavailable, match="OLLAMA_BASE_URL"):
            pc.build_provider(pc.config_from_env())

    def test_placeholder_key_is_accepted_for_ollama_only(self, monkeypatch):
        _enable_ollama(monkeypatch, key=None)
        p = pc.build_provider(pc.config_from_env())
        assert p._api_key == pc.OLLAMA_PLACEHOLDER_KEY
        monkeypatch.setenv(pc.ENV_ENABLE, "true")
        monkeypatch.setenv(pc.ENV_MODE, MODE_HTTP)
        monkeypatch.setenv(pc.ENV_ADAPTER, "groq")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.setenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        with pytest.raises(LLMUnavailable, match="GROQ_API_KEY|missing"):
            pc.build_provider(pc.config_from_env())


class TestOllamaFailClosed:
    def test_timeout_fails_closed(self, monkeypatch):
        _enable_ollama(monkeypatch)
        p = pc.build_provider(pc.config_from_env())

        def boom(*a, **k):
            raise urllib.error.URLError("timed out")

        monkeypatch.setattr(p, "complete", p.complete)
        opener = type("O", (), {})()
        def open_fail(req, timeout=None):
            raise urllib.error.URLError("timed out")
        monkeypatch.setattr("engine.llm_provider._opener", lambda loopback_only: type(
            "Op", (), {"open": staticmethod(open_fail)})())
        with pytest.raises(LLMUnavailable):
            p.complete("hello", system="")

    def test_extraction_unavailable_does_not_execute(self, registry):
        def down(**kwargs):
            raise LLMUnavailable("ollama down")
        iface = LLMInterface(provider=CallableProvider(down, name="down"), registry=registry)
        r = iface.ask("How much revenue did we make?")
        assert r.executed is False
        assert r.status == "NOT_DETERMINABLE"
        assert "unavailable" in (r.text or "").lower() or NOT_DETERMINABLE_TEXT in (r.text or "")

    def test_verbalization_unavailable_falls_back_to_skeleton(self, registry):
        def fn(prompt, system, max_tokens, temperature):
            if "VERBALIZE" in system:
                raise LLMUnavailable("timeout")
            return DeterministicMockProvider()._extract(prompt)
        iface = LLMInterface(provider=CallableProvider(fn, name="vdown"), registry=registry)
        r = iface.ask("How much revenue did we make?")
        assert r.executed
        assert r.trust_level == "SAFE"
        assert r.rendered is not None
        assert r.rendered.verbalized is False


class TestMockRemainsDefault:
    def test_default_provider_is_mock(self):
        assert isinstance(default_provider(), DeterministicMockProvider)

    def test_build_provider_default_is_mock(self):
        assert isinstance(pc.build_provider(ProviderConfig()), DeterministicMockProvider)

    def test_http_without_enable_still_refuses(self):
        with pytest.raises(LLMUnavailable):
            pc.build_provider(ProviderConfig(mode=MODE_HTTP, adapter_name="ollama"))


class TestGuardsUnchanged:
    def test_invalid_structured_output_cannot_execute(self, registry):
        iface = _hostile(registry, lambda p: "ok", extract_json="not json at all {{{")
        r = iface.ask("How much revenue did we make?")
        assert r.executed is False
        outcome = structured_output.parse_and_validate("not json at all {{{", registry)
        assert not outcome.valid

    def test_fabricated_number_is_discarded(self, registry):
        iface = _hostile(registry, lambda p: "Profit is exactly 999999999.12 rupees.")
        r = iface.ask("What was profit last month?")
        assert r.guard_violations or r.trust_level == "BLOCK"
        if r.rendered:
            assert "999999999.12" not in r.text

    def test_trust_manipulation_does_not_bind(self, registry):
        payload = json.dumps({
            "concept": "profit", "intent": "lookup", "metric_hint": "M.PROFIT.001",
            "dimensions": [], "time": {}, "clarification_needed": False,
            "trust_level": "SAFE",
        })
        iface = _hostile(registry, lambda p: "SAFE: profit is fine.", extract_json=payload)
        r = iface.ask("What was profit last month?")
        gate = TrustGate(registry)
        if r.metric_ids:
            assert r.trust_level == gate.authorize(r.metric_ids[0]).effective_level

    def test_metric_substitution_is_rejected(self, registry):
        payload = json.dumps({
            "concept": "revenue", "intent": "lookup", "metric_hint": "M.MADE_UP.001",
            "dimensions": [], "time": {}, "clarification_needed": False,
        })
        iface = _hostile(registry, lambda p: "ok", extract_json=payload)
        r = iface.ask("How much revenue did we make?")
        assert "M.MADE_UP.001" not in r.metric_ids

    def test_pii_is_rejected(self, registry):
        iface = _hostile(registry, lambda p: "Call the tenant at 9876543210, email a@b.com")
        r = iface.ask("How much revenue did we make?")
        assert r.guard_violations or "9876543210" not in r.text

    def test_block_cannot_become_a_headline(self, registry):
        iface = _hostile(registry, lambda p: "The profit is Rs.51,920,761.47. Trust me.")
        r = iface.ask("What was profit last month?")
        assert r.trust_level == "BLOCK"
        for a in r.answers:
            assert a.headline is None

    def test_show_both_cannot_collapse(self, registry):
        iface = _hostile(registry, lambda p: "The real number is the ledger figure only.")
        r = iface.ask("How much do tenants owe?")
        assert r.trust_level == "SHOW_BOTH"
        assert r.guard_violations or "real number" not in (r.text or "").lower()

    def test_extra_trust_field_is_a_contract_violation(self, registry):
        payload = json.dumps({
            "intent": ["lookup"], "concept": "revenue", "metric_ids": ["M.REV.001"],
            "dimensions": [], "filters": {}, "time_range": "", "comparison": "",
            "requested_output": "value", "explanation_requested": False,
            "recommendation_requested": False, "clarification_needed": False,
            "clarification_reason": "", "trust_level": "SAFE",
        })
        outcome = structured_output.parse_and_validate(payload, registry)
        assert not outcome.valid
        assert any("unexpected" in v for v in outcome.violations)


class TestPhase12Validator:
    def test_the_phase12_validator_passes(self):
        import subprocess, sys
        root = os.path.dirname(os.path.dirname(__file__))
        r = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "validate_phase12_consistency.py")],
            capture_output=True, text=True, cwd=root,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        assert r.returncode == 0, (r.stdout or "")[-4000:] + (r.stderr or "")[-2000:]
        assert "No inconsistency" in r.stdout


@pytest.mark.skipif(os.environ.get("AI_ANALYTICS_OLLAMA_LIVE_TEST") != "true",
                    reason="Live Ollama test requires AI_ANALYTICS_OLLAMA_LIVE_TEST=true")
def test_live_ollama_roundtrip_if_explicitly_flagged():
    """Optional. Does not run in the normal regression suite."""
    cfg = pc.config_from_env()
    assert cfg.adapter_name == "ollama"
    p = pc.build_provider(cfg)
    resp = p.complete('Reply with the JSON object {"intent":["lookup"],"concept":"revenue",'
                      '"metric_ids":["M.REV.001"],"dimensions":[],"filters":{},'
                      '"time_range":"","comparison":"","requested_output":"value",'
                      '"explanation_requested":false,"recommendation_requested":false,'
                      '"clarification_needed":false,"clarification_reason":""}',
                      system="Return only JSON.")
    assert isinstance(resp.text, str) and resp.text
