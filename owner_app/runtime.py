"""
runtime.py -- the seam between Streamlit and the existing engine.

Streamlit reruns the whole script on every widget interaction. The analytics engine takes tens of
seconds to reconstruct its payloads from the evidence export, so a naive Streamlit app would
re-run the entire catalogue every time the owner moved a dropdown.

It does not need to. `AnalyticsService` already memoises every payload against the bound source's
descriptor, and the bound source is an IMMUTABLE export whose digest is pinned -- so the payloads
are a pure function of the evidence, and holding one service for the life of the process is the
same correctness argument the FastAPI deployment already relies on. `st.cache_resource` gives
exactly that: one service, shared across reruns and sessions.

WHAT THIS MODULE IS NOT
-----------------------
It is not a calculation layer. Every function here returns a projection the service already
builds. Nothing in `owner_app/` computes a business figure, chooses a definition, reads a trust
level to decide anything, or touches the evidence. If a number appears on screen, the engine
formatted it.

Owner decisions are deliberately NOT cached: they are the one thing in the product that changes
without the evidence changing, and a cached decision log would show an owner their own recorded
preference disappearing until the cache expired.
"""
from __future__ import annotations

import os

import streamlit as st

# The evidence root travels with the package. Set before the engine is imported anywhere, so a
# deployment that unpacks this repository at any path resolves the export beside the code rather
# than at the absolute path of the machine the export was built on.
os.environ.setdefault(
    "AI_ANALYTICS_BASE",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from api.authorization import ROLE_OWNER  # noqa: E402
from api.service import AnalyticsService  # noqa: E402


@st.cache_resource(show_spinner=False)
def service() -> AnalyticsService:
    """The one engine instance this application talks to.

    Constructing it runs the quarantine gate over the bound data source exactly as the API
    deployment does: `ExportDataSource` is revalidated before it may serve, and a source that
    fails stays quarantined. Streamlit changes none of that -- it only holds the result.
    """
    svc = AnalyticsService()
    svc.warm_cache()
    return svc


def source_descriptor():
    """What the application is reading from, for the footer and the technical panel."""
    return service().source.descriptor()


# --- owner-safe projections -------------------------------------------------------------------
#
# Every one of these is a straight pass-through to a service method. They exist so the views name
# what they want rather than reaching into the service, and so the cache key for a filtered
# section is the filter itself.


def owner_home() -> dict:
    return service().owner_home(ROLE_OWNER)


def analytics_sections() -> dict:
    return service().analytics_sections()


def analytics_section(section_key: str, period: str = "", compare: str = "",
                      apartment: str = "") -> dict:
    """One analytics section under the owner's current filters.

    The service memoises per filter combination, so moving a dropdown costs one section build and
    every later visit to the same combination costs nothing. The apartment rule lives in the
    engine: a measure that cannot answer an apartment-scoped question is OMITTED from the payload
    rather than returned with a refusal, so this layer needs no rule of its own and cannot show
    an estate-wide figure under an apartment heading.
    """
    return service().analytics_section(
        section_key, ROLE_OWNER, period=period, compare=compare, apartment=apartment)


def data_quality() -> dict:
    return service().data_quality()


def metric_detail(metric_id: str) -> dict:
    return service().metric_detail(metric_id, ROLE_OWNER)


def conflict_view(metric_id: str) -> dict:
    return service().conflict_view(metric_id, ROLE_OWNER)


def metric_contracts() -> dict:
    return service().metric_contracts(ROLE_OWNER)


def unresolved_definitions() -> dict:
    return service().unresolved_definitions(ROLE_OWNER)


def executive_report() -> dict:
    return service().executive_report()


def export_section(section_key: str, period: str = "", compare: str = "",
                   apartment: str = "") -> dict:
    return service().export_section(
        section_key, ROLE_OWNER, period=period, compare=compare, apartment=apartment)


def decision_log() -> dict:
    """Never cached. A recorded preference must appear the moment it is recorded."""
    return service().decision_log(ROLE_OWNER)


def record_decision(item_key: str, status: str, note: str = "", decided_by: str = "") -> dict:
    """Record where the owner stands on an item.

    Passed straight to the store. It changes no trust level, no definition, no figure and no
    conflict -- the engine never reads it back -- which is why this layer may write it without
    becoming a second authority over anything.
    """
    return service().record_decision(item_key, status, note=note, decided_by=decided_by,
                                     role_id=ROLE_OWNER)


def ask(question: str, conversation_id: str | None = None) -> dict:
    """The natural-language pipeline, unchanged.

    The same `AnalyticsService.ask` every other surface calls: the deterministic engine answers,
    and the language model -- when one is configured -- only re-words the finished answer under
    the existing verbalization guard. There is no second AI pipeline here and no place for one:
    this function passes a string in and renders what comes back.
    """
    from api.authorization import Session
    session = Session(subject="owner", role_id=ROLE_OWNER, display_name="Owner")
    return service().ask(question, session=session, conversation_id=conversation_id)


def revenue_forecast() -> dict | None:
    """The engine's own revenue projection, fetched through the question pipeline.

    Cached for the session because it is a model run over an immutable export, and because a
    Streamlit rerun must not re-run the forecaster every time the owner clicks something. Returns
    None when the engine declines -- a declined forecast is not an empty chart.
    """
    return _forecast_cached()


@st.cache_data(show_spinner=False, ttl=None)
def _forecast_cached() -> dict | None:
    try:
        result = ask("Forecast revenue for the next 3 months")
    except Exception:
        return None
    if not result or not result.get("answer"):
        return None
    if (result.get("trust_level") or "") == "NOT_DETERMINABLE":
        return None
    return result


def llm_status() -> dict:
    """How the language layer is configured, for the technical panel. Never the credential."""
    return service().provider_config.describe()
