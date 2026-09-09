"""
wsgi.py -- the ASGI entry point a hosting platform imports.

`serve.py` is the local developer entry point: it reads a host and port, refuses to start
without either a secret or a local-development flag, and calls uvicorn itself. A platform does
none of that -- it runs its own server process and imports an application object -- so this
module is the seam between the two. It adds no behaviour of its own.

What it DOES do, and why it is not just `app = create_app()`:

The engine reconstructs every owner-facing payload from the evidence export, and that takes
tens of seconds. Left to the first request, the owner's first page load pays for the whole
engine and the platform's request timeout most likely fires first. So the payloads are built
during application STARTUP, before the platform routes any traffic here -- the same warm-up
`serve.py` performs, moved to the lifecycle hook a platform actually uses.

Nothing about trust, evidence, calculation or authentication is decided here.
"""
import os

from api.service import AnalyticsService, create_app

# Constructing the service runs the quarantine gate over the bound data source, exactly as it
# does locally. A source that fails revalidation fails here too, before anything is served.
_service = AnalyticsService()

app = create_app(_service)


@app.on_event("startup")
def _warm() -> None:
    """Build the cached payloads before the first request arrives.

    Failing loudly is deliberate: a service that starts but cannot build its payloads would
    answer every request with an error while reporting itself healthy, and the platform would
    keep it in rotation. Better to fail the deploy.
    """
    built = _service.warm_cache()
    print(f"Owner Intelligence ready: {len(built)} payloads cached "
          f"from {_service.source.descriptor().name}.", flush=True)


@app.get("/healthz", include_in_schema=False)
def healthz():
    """Liveness for the platform and for an uptime pinger.

    Outside /api/, so it needs no identity -- a health check that requires a credential is a
    health check that reports the credential's state rather than the service's. It reports
    whether the payloads are built and which source is bound, and nothing about the business.
    """
    descriptor = _service.source.descriptor()
    return {
        "status": "ok",
        "cached_payloads": len(getattr(_service, "_cache", {}) or {}),
        "source": descriptor.name,
        "source_status": descriptor.status,
        "as_of": descriptor.as_of,
        "env": os.environ.get("AI_ANALYTICS_ENV", ""),
    }
