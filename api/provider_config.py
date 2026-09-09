"""
provider_config.py -- Phase 9 (W4). Config-driven LLM provider selection.

The provider interface already exists (Phase 4 `engine/llm_provider.py`). Phase 9 adds only the
selection and failure policy around it. Nothing here changes what a provider is allowed to do:
it proposes a concept and re-words a finished skeleton, and both are validated downstream.

Three rules this module enforces:

1. **Offline by default.** The deterministic mock is the default provider. A live model is opt-in
   via explicit configuration, never a silent default -- so no test, script, or deployment can
   accidentally require network access or spend credentials.

2. **No credential is read at import time.** Importing this module touches no environment
   variable and opens no connection. Credentials are read only when a live adapter is explicitly
   constructed, which makes accidental activation impossible rather than merely unlikely.

3. **A provider failure degrades to a refusal, never to a guess.** Already guaranteed by
   `LLMInterface`; restated here because the temptation in a production layer is to add a
   "fallback" that answers anyway.

NOT built here: a vendor SDK, an HTTP client, or a live call. `HttpAdapterSpec` describes the
SHAPE a deployment fills in with its own client. Shipping a half-built HTTP caller would invite
someone to finish it without re-reading the guard contract.
"""
import os
from dataclasses import dataclass, field

from engine.llm_provider import (LLMProvider, DeterministicMockProvider, CallableProvider,
                                 LLMUnavailable, OpenAICompatibleProvider,
                                 assert_loopback_endpoint, DEFAULT_HTTP_TIMEOUT)

MODE_OFFLINE = "offline"
MODE_CALLABLE = "callable"
MODE_HTTP = "http"

ALL_MODES = (MODE_OFFLINE, MODE_CALLABLE, MODE_HTTP)

ENV_MODE = "AI_ANALYTICS_LLM_MODE"
ENV_ENABLE = "AI_ANALYTICS_LLM_ENABLE"
ENV_ADAPTER = "AI_ANALYTICS_LLM_ADAPTER"
ENV_TIMEOUT = "AI_ANALYTICS_LLM_TIMEOUT"
RECOMMENDED_TIMEOUT = 180  # demo/Ollama; override via AI_ANALYTICS_LLM_TIMEOUT (1–300)
OLLAMA_PLACEHOLDER_KEY = "ollama"
DESTINATION_NONE = "none"
DESTINATION_LOCAL_LOOPBACK = "local_loopback"
DESTINATION_EXTERNAL = "external"
REMAINING_LLM = (
    "Set AI_ANALYTICS_LLM_ENABLE=true and AI_ANALYTICS_LLM_MODE=http with an adapter name. "
    "Local Ollama: AI_ANALYTICS_LLM_ADAPTER=ollama, OLLAMA_BASE_URL=http://127.0.0.1:11434/v1, "
    "OLLAMA_MODEL=<installed tag>, OLLAMA_API_KEY=ollama. A running Ollama process or a key "
    "is not consent. External adapters (groq, openai-compatible) send data off-machine and "
    "remain separately controlled."
)


@dataclass(frozen=True)
class HttpAdapterSpec:
    """The shape a deployment implements to plug in a real model.

    Deliberately a SPEC and not a client. The integrator supplies the transport; this codebase
    stays free of vendor SDKs, so swapping providers touches nothing below the LLM boundary.
    """
    name: str
    endpoint_env: str            # env var holding the endpoint
    api_key_env: str             # env var holding the credential
    model_env: str = ""
    request_shape: str = ("{system, prompt, max_tokens, temperature} -> {text}")
    notes: str = ""

    def credential_present(self):
        """Whether a deployment has supplied a credential. Reads the environment ONLY when
        called -- never at import."""
        return bool(os.environ.get(self.api_key_env))


# Adapter shapes a deployment may implement. Listing a shape is not enabling it: none of these
# is constructed unless a caller explicitly asks for it and supplies a transport.
KNOWN_ADAPTERS = (
    HttpAdapterSpec(name="anthropic", endpoint_env="ANTHROPIC_BASE_URL",
                    api_key_env="ANTHROPIC_API_KEY", model_env="ANTHROPIC_MODEL",
                    notes="Messages API. The integrator supplies the HTTP client. EXTERNAL."),
    HttpAdapterSpec(name="openai-compatible", endpoint_env="OPENAI_BASE_URL",
                    api_key_env="OPENAI_API_KEY", model_env="OPENAI_MODEL",
                    notes="Any OpenAI-compatible chat-completions endpoint. EXTERNAL unless "
                          "the operator points it at loopback; this adapter is not the local "
                          "Ollama pin."),
    HttpAdapterSpec(name="groq", endpoint_env="GROQ_BASE_URL",
                    api_key_env="GROQ_API_KEY", model_env="GROQ_MODEL",
                    notes="OpenAI-compatible. EXTERNAL. Presence of a credential does NOT "
                          "enable it."),
    HttpAdapterSpec(name="ollama", endpoint_env="OLLAMA_BASE_URL",
                    api_key_env="OLLAMA_API_KEY", model_env="OLLAMA_MODEL",
                    notes="Local OpenAI-compatible /v1/chat/completions. Loopback hosts only. "
                          "Reuses OpenAICompatibleProvider. A running daemon does NOT enable it."),
)


@dataclass
class ProviderConfig:
    mode: str = MODE_OFFLINE
    adapter_name: str = ""
    verbalize: bool = True
    fn: object = None            # for MODE_CALLABLE
    explicitly_enabled: bool = False

    def describe(self):
        enabled = self.explicitly_enabled and self.mode == MODE_HTTP
        local = bool(enabled and self.adapter_name == "ollama")
        external = bool(enabled and not local)
        if local:
            destination = DESTINATION_LOCAL_LOOPBACK
            status = "LOCAL_LOOPBACK"
            note = ("Local Ollama on loopback. Questions and answer skeletons stay on this "
                    "machine. The model remains untrusted: output passes the verbalization "
                    "guard. Destination class: LOCAL LOOPBACK AI, not EXTERNAL NETWORK AI.")
        elif external:
            destination = DESTINATION_EXTERNAL
            status = "EXTERNAL"
            note = ("External HTTP adapter. Business text in prompts may leave the machine. "
                    "The model remains untrusted: output passes the verbalization guard.")
        else:
            destination = DESTINATION_NONE
            status = "QUARANTINED"
            note = ("Offline deterministic provider. No network access, no credentials used.")
        return {
            "mode": self.mode if enabled or self.mode != MODE_HTTP else MODE_OFFLINE,
            "adapter_name": self.adapter_name if enabled else "",
            "verbalize": self.verbalize,
            "network_access": bool(external),
            "local_loopback": bool(local),
            "destination": destination,
            "explicitly_enabled": self.explicitly_enabled,
            "status": status,
            "remaining_requirement": "" if enabled else REMAINING_LLM,
            "note": note,
        }


def adapter(name):
    for a in KNOWN_ADAPTERS:
        if a.name == name:
            return a
    return None


def available_adapters():
    """Adapter shapes and whether a credential happens to be present.

    Reporting `credential_present` is NOT an offer to use it. Business data is not sent to an
    external service because a key exists in the environment -- activation requires explicit
    configuration by the deployment.
    """
    enabled_name = ""
    cfg = None
    try:
        cfg = config_from_env()
        if cfg.explicitly_enabled and cfg.mode == MODE_HTTP:
            enabled_name = cfg.adapter_name
    except Exception:
        enabled_name = ""
    return tuple({
        "name": a.name, "endpoint_env": a.endpoint_env, "api_key_env": a.api_key_env,
        "credential_present": a.credential_present(),
        "enabled": bool(enabled_name) and a.name == enabled_name,
        "note": a.notes,
    } for a in KNOWN_ADAPTERS)


def build_provider(config: ProviderConfig = None) -> LLMProvider:
    """Construct the configured provider. Defaults to offline."""
    config = config or ProviderConfig()

    if config.mode == MODE_OFFLINE:
        return DeterministicMockProvider()

    if config.mode == MODE_CALLABLE:
        if config.fn is None:
            raise LLMUnavailable(
                "MODE_CALLABLE requires a completion function. None was supplied, and this "
                "layer will not substitute one -- an unread question is refused, never guessed.")
        return CallableProvider(config.fn, name=config.adapter_name or "callable")

    if config.mode == MODE_HTTP:
        spec = adapter(config.adapter_name)
        if not config.explicitly_enabled:
            raise LLMUnavailable(
                "HTTP adapter refused: AI_ANALYTICS_LLM_ENABLE is not true. "
                + REMAINING_LLM)
        if spec is None:
            raise LLMUnavailable(
                f"Unknown adapter {config.adapter_name!r}. Known: "
                f"{[a.name for a in KNOWN_ADAPTERS]}.")
        endpoint = os.environ.get(spec.endpoint_env) or ""
        key = os.environ.get(spec.api_key_env) or ""
        model = os.environ.get(spec.model_env) or ""
        if spec.name == "anthropic":
            raise LLMUnavailable(
                "Anthropic is listed as a shape. Use an OpenAI-compatible endpoint via "
                "openai-compatible or groq, or supply MODE_CALLABLE with your own transport.")
        timeout = _timeout_from_env()
        if spec.name == "ollama":
            if not endpoint:
                raise LLMUnavailable(
                    "Ollama adapter requires OLLAMA_BASE_URL "
                    "(http://127.0.0.1:11434/v1). " + REMAINING_LLM)
            if not (model or "").strip():
                raise LLMUnavailable(
                    "Ollama adapter requires OLLAMA_MODEL (an installed local model tag).")
            assert_loopback_endpoint(endpoint)
            return OpenAICompatibleProvider(
                endpoint=endpoint,
                api_key=key or OLLAMA_PLACEHOLDER_KEY,
                model=model.strip(),
                adapter_name="ollama",
                loopback_only=True,
                require_model=True,
                timeout=timeout)
        if not endpoint or not key:
            raise LLMUnavailable(
                f"Adapter {spec.name!r} is explicitly enabled but missing "
                f"{spec.endpoint_env} or {spec.api_key_env}.")
        return OpenAICompatibleProvider(
            endpoint=endpoint, api_key=key, model=model, adapter_name=spec.name,
            timeout=timeout)

    raise LLMUnavailable(f"Unknown provider mode {config.mode!r}. Known: {list(ALL_MODES)}")


def _timeout_from_env():
    raw = (os.environ.get(ENV_TIMEOUT) or "").strip()
    if not raw:
        return RECOMMENDED_TIMEOUT
    try:
        n = float(raw)
    except ValueError:
        return DEFAULT_HTTP_TIMEOUT
    if n <= 0 or n > 300:
        return DEFAULT_HTTP_TIMEOUT
    return n


def config_from_env():
    """Read configuration from the environment. Defaults to offline when unset or unrecognised
    -- an unreadable configuration never silently enables a live model. Enable must be the
    exact string 'true'."""
    enabled = (os.environ.get(ENV_ENABLE) or "").strip() == "true"
    mode = (os.environ.get(ENV_MODE) or MODE_OFFLINE).strip().lower()
    if mode not in ALL_MODES:
        mode = MODE_OFFLINE
    adapter_name = (os.environ.get(ENV_ADAPTER) or "").strip()
    if not enabled:
        return ProviderConfig(mode=MODE_OFFLINE, explicitly_enabled=False)
    return ProviderConfig(mode=mode, adapter_name=adapter_name, explicitly_enabled=True)
