"""
serve.py -- run the Owner Intelligence application.

    python serve.py                      # offline: deterministic wording, no model needed
    ... with the Phase 12 environment set # local Ollama supplies the wording

Reads configuration from the environment and starts nothing that the environment did not ask
for. In particular it enables no LLM adapter and connects to no live database: both remain
opt-in through their own Phase 12 / Phase 13 activation paths.

An auth secret is required for normal use. There is no default, because a default secret is a
shared secret. Local development may set AI_ANALYTICS_AUTH_DISABLE=true (only when
AI_ANALYTICS_ENV is unset/local/development/dev) to skip the bearer prompt in the browser.
"""
import os
import sys

from api.auth import (ENV_SECRET, ENV_AUTH_DISABLE, ENV_NAME,
                      auth_disable_requested, auth_disable_allowed)

REQUIRED = (
    f"Set {ENV_SECRET} to a private random string before serving, e.g.\n"
    f"    PowerShell:  $env:{ENV_SECRET} = (New-Guid).Guid\n"
    f"    bash:        export {ENV_SECRET}=$(python -c \"import uuid;print(uuid.uuid4())\")\n"
    f"Or for local browser UAT only:\n"
    f"    $env:{ENV_AUTH_DISABLE} = 'true'   # requires {ENV_NAME} unset/local/development/dev\n"
    f"Without a secret (or a permitted local disable) the API refuses every request rather "
    f"than serving one unauthenticated."
)


def main():
    local_open = auth_disable_requested() and auth_disable_allowed()
    if auth_disable_requested() and not auth_disable_allowed():
        print(
            f"{ENV_AUTH_DISABLE}=true is ignored when {ENV_NAME}="
            f"{(os.environ.get(ENV_NAME) or '').strip()!r}. "
            f"Use a local environment name, or set {ENV_SECRET}.",
            file=sys.stderr,
        )
        return 2
    if not os.environ.get(ENV_SECRET) and not local_open:
        print(REQUIRED, file=sys.stderr)
        return 2

    # The rupee sign is not representable in the Windows console's default code page, and every
    # figure this application prints carries one.
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    import uvicorn
    from api.service import AnalyticsService, create_app

    host = os.environ.get("AI_ANALYTICS_HOST", "127.0.0.1")
    port = int(os.environ.get("AI_ANALYTICS_PORT", "8000"))

    service = AnalyticsService()
    app = create_app(service)

    # Build the owner-facing payloads before accepting traffic. The bound evidence is an
    # immutable export, so these are computed once and served from memory; without this the
    # owner's first page pays for the whole engine.
    print("Building analytics from the trusted export...")
    built = service.warm_cache()
    print(f"Ready: {len(built)} payloads cached.")
    if local_open:
        print("Auth: LOCAL open (AI_ANALYTICS_AUTH_DISABLE=true) — not for production.")
    print(f"Owner Intelligence on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
