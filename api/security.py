"""
security.py -- Phase 11. CORS, headers, rate-limit hook, error sanitization, secret scan.
"""
from __future__ import annotations

import os
import re
import time
from collections import defaultdict

ENV_CORS = "AI_ANALYTICS_CORS_ORIGINS"
ENV_NAME = "AI_ANALYTICS_ENV"
ENV_RATE = "AI_ANALYTICS_RATE_LIMIT"
DEFAULT_RATE = 120          # requests
DEFAULT_WINDOW = 60.0       # seconds
MAX_QUESTION_CHARS = int(os.environ.get("AI_ANALYTICS_MAX_QUESTION_CHARS") or 4000)

_LEAK = re.compile(
    r"(?i)(api[_-]?key|authorization:|bearer\s+[A-Za-z0-9\-._]+|"
    r"postgres(?:ql)?://|mongodb://|supabase\.co|"
    r"[A-Za-z]:\\[^\s]+|/home/[^\s]+|/Users/[^\s]+|"
    r"-----BEGIN|"
    r"\b(SELECT|INSERT|UPDATE|DELETE)\b.+\bFROM\b)"
)


class RateLimiter:
    """In-memory token bucket. A deployment may substitute another object with allow()."""

    def __init__(self, limit=DEFAULT_RATE, window=DEFAULT_WINDOW, disabled=False):
        self.limit = int(os.environ.get(ENV_RATE) or limit)
        self.window = window
        self.disabled = disabled
        self._hits = defaultdict(list)

    def allow(self, key: str) -> bool:
        if self.disabled:
            return True
        now = time.time()
        bucket = self._hits[key]
        cutoff = now - self.window
        self._hits[key] = [t for t in bucket if t > cutoff]
        if len(self._hits[key]) >= self.limit:
            return False
        self._hits[key].append(now)
        return True


def cors_origins():
    raw = (os.environ.get(ENV_CORS) or "").strip()
    if not raw:
        return ()
    origins = tuple(o.strip() for o in raw.split(",") if o.strip())
    if "*" in origins and (os.environ.get(ENV_NAME) or "").lower() == "production":
        raise RuntimeError("Wildcard CORS is refused when AI_ANALYTICS_ENV=production.")
    return origins


def security_headers(request_id: str):
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "X-Request-ID": request_id,
        "Cache-Control": "no-store",
    }


def sanitize_error(exc: BaseException) -> str:
    """Public error text. Never a path, SQL fragment, or secret."""
    name = type(exc).__name__
    if name in ("AuthenticationError",):
        return "Authentication required."
    if name in ("AuthorizationError",):
        return "Not authorized for this role."
    if name in ("QuarantineError", "DataSourceError"):
        return "The data source is not available to the engine."
    return "The request could not be completed."


def contains_secret_material(text: str, extra_secrets=()) -> bool:
    if not text:
        return False
    if _LEAK.search(text):
        return True
    for s in extra_secrets:
        if s and str(s) and str(s) in text:
            return True
    return False


def collect_configured_secrets():
    keys = (
        "AI_ANALYTICS_AUTH_SECRET", "GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_READONLY_KEY",
        "SUPABASE_URL", "DATABASE_URL", "SUPABASE_DB_URL",
    )
    return tuple(os.environ[k] for k in keys if os.environ.get(k))
