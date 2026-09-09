"""
validate_phase12_consistency.py -- Phase 12 anti-drift validator.

  1. source CSVs byte-identical
  2. metric / conflict / DQ registries byte-identical
  3. default provider is still the mock
  4. Ollama is loopback-only
  5. no second pipeline (no native /api/chat client, no RAG/tools/SQL from provider)
  6. Trust Gate / Answer Contract modules do not import Ollama
  7. external adapters remain separately controlled
  8. enable is explicit
  9. Phase 12 artifacts exist
"""
import csv
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.llm_provider import (DeterministicMockProvider, default_provider,
                                 assert_loopback_endpoint, LLMUnavailable)
from engine.gate import TrustGate
from engine.semantic_registry import SemanticRegistry
from api import provider_config as pc
from api.provider_config import ProviderConfig, MODE_HTTP

BASELINE_SHA = "aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26"
REGISTRY_SHA = {
    "semantic_metric_registry.csv":
        "de9e8acf87c4bb200fb25d7cc9b73a7bc1576bbff97941a5725da94292e4c393",
    "conflict_disclosure_registry.csv":
        "12f636c1d22728b7e34c2bde23ce77c0d73c775f5914d4a346824f055d8885b4",
    "data_quality_registry.csv":
        "caed9805b97d767ef9d2e82557bdf266ed7629fed8e84668e266feff690b3690",
}
ARTIFACTS = (
    "phase12_local_llm_spec.md", "phase12_implementation_plan.md", "phase12_report.md",
)
UNTOUCHED = (
    "engine/gate.py", "engine/contract.py", "engine/execution.py",
    "engine/llm_interface.py", "engine/structured_output.py", "engine/answer_renderer.py",
)


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    problems, warnings = [], []

    with open(os.path.join(ROOT, "evidence", "file_manifest.csv"), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    h = hashlib.sha256()
    for r in rows:
        p = os.path.join(ROOT, r["file"])
        if not os.path.exists(p):
            problems.append(f"[1] missing source CSV {r['file']}")
            continue
        with open(p, "rb") as fh:
            h.update(fh.read())
    digest = h.hexdigest()
    if digest != BASELINE_SHA:
        problems.append(f"[1] SOURCE CSVs CHANGED: {digest} != {BASELINE_SHA}")

    for name, expected in REGISTRY_SHA.items():
        actual = _sha_file(os.path.join(ROOT, name))
        if actual != expected:
            problems.append(f"[2] {name} changed ({actual} != {expected})")

    if not isinstance(default_provider(), DeterministicMockProvider):
        problems.append("[3] default_provider is not DeterministicMockProvider")
    if not isinstance(pc.build_provider(ProviderConfig()), DeterministicMockProvider):
        problems.append("[3] build_provider() default is not the mock")

    try:
        assert_loopback_endpoint("https://api.openai.com/v1")
        problems.append("[4] OpenAI URL was accepted as an Ollama endpoint")
    except LLMUnavailable:
        pass
    try:
        assert_loopback_endpoint("http://192.168.0.5:11434/v1")
        problems.append("[4] LAN host was accepted as an Ollama endpoint")
    except LLMUnavailable:
        pass
    try:
        assert_loopback_endpoint("http://127.0.0.1:11434/v1")
    except LLMUnavailable as e:
        problems.append(f"[4] loopback URL refused: {e}")

    prov_src = open(os.path.join(ROOT, "engine", "llm_provider.py"), encoding="utf-8").read()
    cfg_src = open(os.path.join(ROOT, "api", "provider_config.py"), encoding="utf-8").read()
    if "loopback_only" not in prov_src:
        problems.append("[4] OpenAICompatibleProvider has no loopback_only pin")
    if 'name="ollama"' not in cfg_src and "name='ollama'" not in cfg_src:
        problems.append("[4] ollama adapter spec is missing")
    if "/api/generate" in prov_src:
        problems.append("[5] native Ollama /api/generate client was added")
    if "tool_choice" in prov_src or "function_call" in prov_src:
        problems.append("[5] tool/function-calling path was added to the provider")
    if "langchain" in (prov_src + cfg_src).lower():
        problems.append("[5] langchain path was added")

    for rel in UNTOUCHED:
        src = open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8").read()
        if "ollama" in src.lower() or "OLLAMA_" in src:
            problems.append(f"[6] {rel} must not reference Ollama")

    registry = SemanticRegistry()
    gate = TrustGate(registry)
    if gate.authorize("M.PROFIT.001").effective_level != "BLOCK":
        problems.append("[6] Trust Gate is no longer authoritative for M.PROFIT.001")
    if gate.authorize("M.OCC.001").effective_level != "SHOW_BOTH":
        problems.append("[6] Trust Gate is no longer authoritative for M.OCC.001")

    names = [a["name"] for a in pc.available_adapters()]
    if "ollama" not in names or "groq" not in names:
        problems.append("[7] adapter list is missing ollama or groq")
    for a in pc.available_adapters():
        if a["name"] == "ollama" and a["enabled"] and (
                os.environ.get(pc.ENV_ENABLE) or "").lower() != "true":
            problems.append("[7] ollama reported enabled without AI_ANALYTICS_LLM_ENABLE=true")
        if a["name"] in ("groq", "openai-compatible") and a["enabled"] and (
                os.environ.get(pc.ENV_ADAPTER) or "") == "ollama":
            problems.append("[7] an external adapter is enabled while ollama is selected")

    try:
        pc.build_provider(ProviderConfig(mode=MODE_HTTP, adapter_name="ollama"))
        problems.append("[8] Ollama HTTP adapter constructed without explicit enable")
    except LLMUnavailable:
        pass

    for a in ARTIFACTS:
        if not os.path.exists(os.path.join(ROOT, a)):
            problems.append(f"[9] missing {a}")

    iface = open(os.path.join(ROOT, "engine", "llm_interface.py"), encoding="utf-8").read()
    if iface.count("provider.complete") < 2 and iface.count("self.provider.complete") < 2:
        problems.append("[5] LLMInterface no longer calls provider.complete for both roles")

    print("=" * 88)
    print("PHASE 12 CONSISTENCY VALIDATION -- local Ollama vs. the existing engine")
    print("=" * 88)
    print(f"\n[source]        SHA-256 {digest[:16]}... "
          f"{'MATCHES baseline' if digest == BASELINE_SHA else 'CHANGED'}")
    print(f"[mock default]  {isinstance(default_provider(), DeterministicMockProvider)}")
    print(f"[problems]      {len(problems)}")
    print(f"[warnings]      {len(warnings)}")
    if problems:
        print("\nINCONSISTENCIES:")
        for p in problems:
            print(f"   {p}")
    else:
        print("\nNo inconsistency between Phase 12 Ollama activation and the engine.")
    for w in warnings:
        print(f"   warning: {w}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
