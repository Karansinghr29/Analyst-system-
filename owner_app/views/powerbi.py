"""
powerbi.py -- the analyst experience: KPIs, trends, breakdowns, comparison, movement, variance,
attention and definitions, on one page under one set of filters.

It composes the SAME payloads the other pages use -- `owner_home` for the estate-wide feed,
`analytics_section` for anything narrowed -- exactly as the existing Power BI module does. It is
not a second engine and holds no second copy of any rule.

The one rule worth naming again is the narrowing rule, because it is what makes the apartment view
trustworthy: whenever any filter is applied, the SECTION payload is authoritative even when it
comes back empty. Falling back to the estate-wide feed for an empty filtered section is exactly
how an estate figure ends up under an apartment heading, and there is no such fallback here.
"""
from __future__ import annotations

import streamlit as st

from owner_app import runtime, ui
from owner_app.views.analytics import filter_bar

PAGES = {
    "executive": ("Executive", "financial",
                  "The whole business at a glance: what the figures are, how they moved, and "
                  "what is waiting on a decision."),
    "financial": ("Financial", "financial",
                  "Money in, money owed, and what the ledger can prove about profitability."),
    "operations": ("Operations", "operations",
                   "How the property is running day to day."),
    "risk": ("Risk & data quality", "risk",
             "What the records say about their own reliability."),
}


def render() -> None:
    st.title("Analytics workspace")

    keys = list(PAGES)
    labels = [PAGES[k][0] for k in keys]
    chosen_label = st.radio("View", labels, horizontal=True, key="bi-page")
    page_key = keys[labels.index(chosen_label)]
    title, section_key, purpose = PAGES[page_key]

    st.caption(purpose)

    base = runtime.analytics_section(section_key)
    filters = filter_bar(f"bi-{page_key}", base.get("filter_options") or {})
    payload = runtime.analytics_section(section_key, **filters)
    home = runtime.owner_home()
    narrowed = any(filters.values())

    ui.as_of_line(payload)
    if filters["apartment"]:
        st.info(f"Narrowed to apartment {filters['apartment']}. Measures the records do not hold "
                f"per apartment are not listed rather than shown with an estate-wide figure.")

    _kpis(page_key, payload, home, narrowed, filters)
    _trends(page_key, payload, filters)
    _movements(payload, home, narrowed)
    _definitions(payload)
    _attention(payload, home, narrowed)

    ui.limitations(payload.get("limitations") or home.get("limitations"))


def _kpis(page_key: str, payload: dict, home: dict, narrowed: bool, filters: dict) -> None:
    """The measures this view leads with.

    Unnarrowed, the executive view reads the estate the way Owner Home does. Narrowed, it reads
    the section payload -- the only payload that has been through the filter.
    """
    if page_key == "executive" and not narrowed:
        tiles = list(home.get("business_health") or []) + list(home.get("operations") or []) \
            + list(home.get("risks") or [])
    else:
        tiles = payload.get("tiles") or []

    ui.section_heading("Where the business stands", count=len(tiles))
    if not tiles:
        st.info("No measure in this view can answer the question as narrowed.")
        return
    ui.tile_grid(tiles, columns=4, key_prefix=f"bi-{page_key}-{filters['apartment']}")


def _trends(page_key: str, payload: dict, filters: dict) -> None:
    tiles = payload.get("tiles") or []
    series_tiles = [t for t in tiles if ui.month_series(t)]
    breakdowns = [t for t in tiles
                  if not ui.month_series(t) and isinstance(t.get("value"), dict)]

    if series_tiles:
        ui.section_heading("How it moved over time",
                           note="Every point is a recorded month. Nothing is projected here.")
        for tile in series_tiles:
            st.markdown(f"**{tile.get('business_name') or tile.get('title')}**")
            ui.trend_chart(tile,
                           key=f"bi-{page_key}-{tile.get('metric_id')}-{filters['apartment']}")
            if tile.get("owner_caveat"):
                st.caption(tile["owner_caveat"])

    if breakdowns:
        ui.section_heading("Where it came from")
        for tile in breakdowns:
            st.markdown(f"**{tile.get('business_name') or tile.get('title')}**")
            ui.breakdown_chart(tile, key=f"bi-break-{page_key}-{tile.get('metric_id')}")

    # Estate-wide only: there is no apartment forecast, so under an apartment filter the
    # projection is omitted rather than implied to apply.
    if page_key in ("executive", "financial") and not filters["apartment"]:
        ui.section_heading("What is projected")
        ui.forecast_panel(runtime.revenue_forecast())


def _movements(payload: dict, home: dict, narrowed: bool) -> None:
    changes = payload.get("changes") if narrowed else (
        payload.get("changes") or home.get("changes"))
    changes = changes or []
    ui.section_heading("What changed", count=len(changes),
                       note="Supported period comparisons only, between complete months.")
    if not changes:
        st.info("No month-to-month comparison is supported here. Only complete months are "
                "compared, so a part-month is never presented as a movement.")
        return
    for change in changes:
        ui.movement_card(change)


def _definitions(payload: dict) -> None:
    """Measures whose evidence carries competing definitions, shown in full.

    Never collapsed, never ordered by preference: the gate refused to choose between them and so
    does this page.
    """
    conflicted = [t for t in (payload.get("tiles") or [])
                  if t.get("definitions") and not t.get("headline_permitted")]
    if not conflicted:
        return
    ui.section_heading("Where the definitions disagree", count=len(conflicted))
    for tile in conflicted:
        with st.container(border=True):
            st.markdown(f"**{tile.get('business_name') or tile.get('title')}**")
            st.caption(tile.get("posture_line")
                       or (tile.get("trust") or {}).get("owner_label", ""))
            st.write((tile.get("trust") or {}).get("owner_explanation", ""))
            for label, value, parts in ui._definitions(tile):
                # A composite definition is its named parts. Printing the formatted string too
                # put the engine's own field names -- "ar_balance", "deposit_held" -- on screen
                # beside the parts that exist to replace them.
                if parts:
                    st.write(f"- **{label}**")
                    for part in parts:
                        st.caption(f"    {part.get('label', '')} — {part.get('value', '')}")
                else:
                    st.write(f"- **{label}** — {value}" if value else f"- **{label}**")


def _attention(payload: dict, home: dict, narrowed: bool) -> None:
    insights = payload.get("insights") if narrowed else (
        payload.get("insights") or home.get("needs_attention"))
    insights = insights or []
    if not insights:
        return
    ui.section_heading("What management should look at", count=len(insights),
                       note="Grouped by what each item asks for. No priority score exists in "
                            "the records, so none is applied.")
    for card in insights:
        ui.insight_card(card)
