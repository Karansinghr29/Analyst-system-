"""
llm_provider.py -- Phase 4. The LLM provider abstraction.

Requirement: "Do not hard-code the implementation to one provider. Create a provider interface
so the actual model can later be swapped without changing: semantic layer, analytics engine,
trust gate, validation, answer contract."

The interface is deliberately tiny -- one method, text in / text out. Everything that makes the
system safe (schema validation, trust gating, execution, validation, rendering guards) lives
OUTSIDE the provider, so swapping providers cannot weaken any guarantee. A provider is treated
as an untrusted text source throughout: nothing it returns is executed, and everything it
returns is validated before use.

`DeterministicMockProvider` implements the full contract with no network access, so the entire
Phase 4 suite runs without credentials, per the brief: "If no real LLM credentials are
available, implement a deterministic/mock provider and test the complete contract end-to-end.
Do NOT require live API access merely to pass the Phase 4 test suite."
"""
import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class LLMUnavailable(Exception):
    """Raised when a provider cannot serve a request (no credentials, network refused, etc.).
    Callers must degrade to a deterministic path -- never to a guess."""


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str = ""
    raw: dict = field(default_factory=dict)


class LLMProvider(ABC):
    """The entire surface a model implementation must satisfy."""

    name = "abstract"

    @abstractmethod
    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024,
                 temperature: float = 0.0) -> LLMResponse:
        ...

    def available(self) -> bool:
        return True


# --------------------------------------------------------------------------------------------
# Deterministic mock -- the default provider for tests and for offline operation.
# --------------------------------------------------------------------------------------------

class DeterministicMockProvider(LLMProvider):
    """Behaves like a competent, cooperative model: it reads the question, resolves a concept
    using the SAME deterministic concept map the Phase 3 layer uses, and emits a conforming
    JSON plan request. It has no privileged access -- it produces exactly the JSON a real model
    would, and that JSON goes through the identical validation path.

    `scripted` lets a test force a specific raw output (including deliberately malformed or
    adversarial output) so the validation and trust boundaries can be exercised against a
    hostile model, not merely a cooperative one.
    """

    name = "deterministic-mock"

    def __init__(self, scripted=None, verbalizer=None):
        self.scripted = list(scripted) if scripted else None
        self.verbalizer = verbalizer
        self.calls = []

    def complete(self, prompt, *, system="", max_tokens=1024, temperature=0.0):
        self.calls.append({"prompt": prompt, "system": system})

        if self.scripted:
            return LLMResponse(text=self.scripted.pop(0), provider=self.name)

        if "VERBALIZE" in system or "VERBALIZE" in prompt:
            return LLMResponse(text=self._verbalize(prompt), provider=self.name)
        return LLMResponse(text=self._extract(prompt), provider=self.name)

    # -- plan extraction --------------------------------------------------------------------

    def _extract(self, prompt):
        """Produce a plan request from the question embedded in the prompt. Uses the Phase 3
        concept matcher, i.e. exactly the deterministic vocabulary the prompt itself declares
        as the only allowed values."""
        from engine import concept_map
        from engine.question_understanding import classify_intents
        from engine import dimension_resolution as dimres

        question = _extract_question(prompt)
        from engine.question_normalize import normalize_owner_question
        question, _ = normalize_owner_question(question)
        hits = concept_map.match(question)
        intents = classify_intents(question)
        dims = dimres.extract(question)

        concept = hits[0][0].name if hits else None
        metric_ids = list(hits[0][0].metric_ids) if hits else []

        # A cooperative model reports ambiguity rather than picking. Distinct concepts matching
        # one question is exactly the case the resolver must not settle. It ALSO reports when it
        # matched nothing at all -- the prompt instructs exactly that, rather than inventing a
        # nearby concept. Whether "matched nothing" means ambiguous or structurally absent is
        # then decided by the deterministic layer, not here.
        distinct = {c.name for c, _ in hits}
        clarification_needed = len(distinct) > 1 or not hits

        payload = {
            "intent": list(intents),
            "concept": concept,
            "metric_ids": metric_ids,
            "dimensions": list(dims.group_by),
            "filters": dict(dims.filters),
            "time_range": _time_phrase(question),
            "comparison": _comparison_phrase(question),
            "requested_output": _requested_output(intents),
            "explanation_requested": "driver" in intents or "why" in question.lower(),
            "recommendation_requested": "recommendation" in intents,
            "clarification_needed": clarification_needed,
            "clarification_reason": ("more than one distinct business concept matched"
                                     if clarification_needed else ""),
        }
        return json.dumps(payload, indent=2)

    # -- verbalization ----------------------------------------------------------------------

    def _verbalize(self, prompt):
        """A cooperative model restates the deterministic skeleton it was given. It adds no
        numbers of its own -- every figure in the output came from the skeleton."""
        if self.verbalizer is not None:
            return self.verbalizer(prompt)
        marker = "ANSWER SKELETON"
        if marker in prompt:
            skeleton = prompt.split(marker, 1)[1]
            return skeleton.strip()
        return prompt.strip()


def _extract_question(prompt):
    for marker in ("USER QUESTION:", "QUESTION:"):
        if marker in prompt:
            tail = prompt.split(marker, 1)[1].strip()
            return tail.split("\n")[0].strip()
    return prompt.strip().split("\n")[0]


def _time_phrase(question):
    q = question.lower()
    for phrase in ("next month", "next year", "next quarter", "last month", "this month",
                   "last year", "this year", "last quarter", "year to date", "ytd",
                   "forecast", "prediction"):
        if phrase in q:
            return phrase
    import re
    m = re.search(r"\b(\d{4}-\d{2}(?:-\d{2})?)\b", q)
    if m:
        return m.group(1)
    m = re.search(r"\b(20\d{2})\b", q)
    if m:
        return m.group(1)
    for month in ("january", "february", "march", "april", "may", "june", "july", "august",
                  "september", "october", "november", "december"):
        if month in q:
            return month
    return ""


def _comparison_phrase(question):
    q = question.lower()
    for phrase in ("year on year", "year-on-year", "yoy", "compared to", "versus", " vs ",
                   "better than", "worse than", "month on month"):
        if phrase in q:
            return phrase.strip()
    return ""


def _requested_output(intents):
    if "recommendation" in intents:
        return "recommendation"
    if "driver" in intents:
        return "diagnosis"
    if "risk_scan" in intents:
        return "summary"
    if "meta" in intents:
        return "explanation"
    if "trend" in intents or "comparison" in intents or "anomaly" in intents:
        return "explanation"
    return "value"


# --------------------------------------------------------------------------------------------
# Real-provider adapter.
# --------------------------------------------------------------------------------------------

class CallableProvider(LLMProvider):
    """Adapts any callable `fn(prompt, system, max_tokens, temperature) -> str` into a provider.

    This is how a real model is plugged in without this codebase depending on any vendor SDK:
    the integrator supplies the callable. No network code, no vendor client, and no API key
    handling lives here -- deliberately, so that swapping providers touches nothing but the
    callable passed in at construction.
    """

    def __init__(self, fn, name="callable", model=""):
        self._fn = fn
        self.name = name
        self.model = model

    def complete(self, prompt, *, system="", max_tokens=1024, temperature=0.0):
        try:
            text = self._fn(prompt=prompt, system=system, max_tokens=max_tokens,
                            temperature=temperature)
        except Exception as e:                                   # provider-side failure
            raise LLMUnavailable(f"{self.name}: {e}") from e
        if not isinstance(text, str):
            raise LLMUnavailable(f"{self.name}: provider returned {type(text).__name__}, "
                                 f"expected str")
        return LLMResponse(text=text, provider=self.name, model=self.model)


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
CLOUD_HOST_MARKERS = (
    "openai.com", "api.openai.com", "groq.com", "api.groq.com",
    "anthropic.com", "googleapis.com", "openrouter.ai",
)
DEFAULT_HTTP_TIMEOUT = 60


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower().rstrip(".")
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    return h in LOOPBACK_HOSTS


def assert_loopback_endpoint(url: str):
    """Ollama may only target loopback. Cloud and LAN hosts are refused before any POST."""
    from urllib.parse import urlparse
    raw = (url or "").strip()
    if not raw:
        raise LLMUnavailable("Ollama adapter requires OLLAMA_BASE_URL.")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise LLMUnavailable(
            f"Ollama adapter refused scheme {parsed.scheme!r}. Use http://127.0.0.1:11434/v1.")
    host = parsed.hostname or ""
    hay = (parsed.netloc or host).lower()
    if any(marker in hay for marker in CLOUD_HOST_MARKERS):
        raise LLMUnavailable(
            f"Ollama adapter refuses cloud endpoints ({host!r}). Use loopback only.")
    if not is_loopback_host(host):
        raise LLMUnavailable(
            f"Ollama adapter is loopback-only; refused host {host!r}. "
            f"Allowed: 127.0.0.1, localhost, ::1.")


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Local Ollama must not follow a 30x off the box."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code, f"HTTP redirects are disabled ({code} -> {newurl})",
            headers, fp)


def _opener(loopback_only: bool):
    if loopback_only:
        return urllib.request.build_opener(_RefuseRedirects)
    return urllib.request.build_opener()


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible chat-completions over HTTP(S). Constructed only after the
    explicit-enable gate. Failures raise LLMUnavailable. When loopback_only=True (Ollama),
    the destination is pinned to 127.0.0.1 / localhost / ::1 and redirects are refused."""

    name = "openai-compatible"

    def __init__(self, endpoint: str, api_key: str, model: str = "", adapter_name="http",
                 loopback_only: bool = False, require_model: bool = False, timeout: float = None):
        if not endpoint:
            raise LLMUnavailable("HTTP provider requires an endpoint.")
        if loopback_only:
            assert_loopback_endpoint(endpoint)
        if require_model and not (model or "").strip():
            raise LLMUnavailable(
                "Ollama adapter requires OLLAMA_MODEL (an installed local model tag).")
        if not api_key:
            raise LLMUnavailable("HTTP provider requires an API key.")
        self.endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self.model = (model or "").strip() or "unspecified"
        self.name = adapter_name
        self.loopback_only = bool(loopback_only)
        self.timeout = DEFAULT_HTTP_TIMEOUT if timeout is None else float(timeout)

    def complete(self, prompt, *, system="", max_tokens=1024, temperature=0.0):
        url = self.endpoint
        if not url.endswith("/chat/completions"):
            url = url + "/chat/completions"
        if self.loopback_only:
            assert_loopback_endpoint(url)
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": (
                ([{"role": "system", "content": system}] if system else [])
                + [{"role": "user", "content": prompt}]
            ),
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            opener = _opener(self.loopback_only)
            with opener.open(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise LLMUnavailable(f"{self.name}: HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise LLMUnavailable(f"{self.name}: {e.reason}") from e
        except LLMUnavailable:
            raise
        except Exception as e:
            raise LLMUnavailable(f"{self.name}: {e}") from e
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMUnavailable(f"{self.name}: unexpected response shape") from e
        if not isinstance(text, str):
            raise LLMUnavailable(f"{self.name}: content was not text")
        return LLMResponse(text=text, provider=self.name, model=self.model, raw={"ok": True})


def default_provider():
    """The provider used when a caller supplies none. Deterministic and offline by default:
    a live model is opt-in, never the silent default, so no test or script can accidentally
    depend on network access or spend credentials."""
    if os.environ.get("AI_ANALYTICS_LLM") in (None, "", "mock"):
        return DeterministicMockProvider()
    raise LLMUnavailable(
        f"AI_ANALYTICS_LLM={os.environ.get('AI_ANALYTICS_LLM')!r} requests a live provider, but "
        f"this build ships no vendor client. Construct a CallableProvider with your own "
        f"completion function and pass it to LLMInterface(provider=...)."
    )
