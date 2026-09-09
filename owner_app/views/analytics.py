"""
analytics.py -- the Financial, Operations and Risk & Data Quality sections.

One renderer for all three, because they ARE one thing in the engine: `analytics_section` answers
each of them from the same path with the same filters, and the difference between them is which
measures the section holds. Writing three near-identical pages would be three places for the
apartment rule to drift.

THE APARTMENT RULE lives in the engine and is worth restating because it is what keeps this page
honest: under an apartment filter, a measure the records do not hold per apartment is OMITTED from
the payload. It is not returned with an estate-wide figure, and it is not returned with a refusal
card. So this view renders whatever arrives, and cannot show an estate figure under an apartment
heading -- there is no code path here that could.
"""
from __future__ import annotations

import streamlit as st

from owner_app import runtime, ui

SECTION_TITLES = {
    "financial": "Financial",
    "operations": "Operations",
    "risk": "Risk & Data Quality",
}


def filter_bar(section_key: str, options: dict) -> dict:
    """Period, comparison period and apartment, offered from the engine's own option lists.

    Every choice comes from `filter_options`: the months the records actually cover, the
    comparison modes the engine says are available, and the apartments it recognises. Nothing
    here invents an option, and a comparison the engine marked unavailable is shown as
    unavailable with the engine's reason rather than silently omitted.
    """
    months = options.get("months") or []
    apartments = options.get("apartments") or []
    modes = options.get("comparison_modes") or []

    left, middle, right = st.columns(3)

    period = left.selectbox(
        "Period", ["All recorded months"] + months, key=f"period-{section_key}")
    period = "" if period == "All recorded months" else period

    mode_labels = ["No comparison"] + [m.get("label", "") for m in modes if m.get("label")]
    chosen_label = middle.selectbox("Compare with", mode_labels, key=f"compare-{section_key}")
    compare = ""
    if chosen_label != "No comparison":
        mode = next((m for m in modes if m.get("label") == chosen_label), None)
        if mode:
            if mode.get("key") == "custom":
                compare = middle.selectbox("Comparison month", [""] + months,
                                           key=f"compare-month-{section_key}")
            elif mode.get("available"):
                compare = mode.get("period", "")
            elif mode.get("unavailable_reason"):
                middle.caption(mode["unavailable_reason"])

    apartment = right.selectbox(
        "Apartment", ["All apartments"] + apartments, key=f"apartment-{section_key}")
    apartment = "" if apartment == "All apartments" else apartment

    if apartment and options.get("apartment_note"):
        st.caption(options["apartment_note"])

    return {"period": period, "compare": compare, "apartment": apartment}


def render(section_key: str) -> None:
    # An unfiltered fetch first, only to learn what the filter bar may offer. The service
    # memoises it, so this costs nothing on a rerun.
    base = runtime.analytics_section(section_key)
    if not base.get("available", True):
        st.warning(base.get("reason") or "This section is not available.")
        return

    st.title(base.get("title") or SECTION_TITLES.get(section_key, section_key.title()))
    if base.get("purpose"):
        st.caption(base["purpose"])

    filters = filter_bar(section_key, base.get("filter_options") or {})
    payload = runtime.analytics_section(section_key, **filters)

    ui.as_of_line(payload)
    if filters["apartment"]:
        st.info(f"Showing only what the records can answer for apartment "
                f"{filters['apartment']}. A measure that is not held per apartment is not "
                f"listed here rather than being shown with an estate-wide figure.")

    tiles = payload.get("tiles") or []
    ui.section_heading("Measures", count=len(tiles))
    if not tiles:
        st.info("No measure in this section can answer the question as narrowed.")
    else:
        ui.tile_grid(tiles, columns=3, key_prefix=f"{section_key}-{filters['apartment']}")

    _charts(section_key, tiles, filters)
    _movements(payload)
    _findings(payload)
    _export(section_key, filters, payload)

    ui.limitations(payload.get("limitations"))
    _capabilities(payload)


def _charts(section_key: str, tiles: list, filters: dict) -> None:
    """Series and breakdowns the payload already carries."""
    series_tiles = [t for t in tiles if ui.month_series(t)]
    breakdown_tiles = [t for t in tiles
                       if not ui.month_series(t) and isinstance(t.get("value"), dict)]
    if not series_tiles and not breakdown_tiles:
        return

    ui.section_heading("Over time and by category")
    for tile in series_tiles:
        st.markdown(f"**{tile.get('business_name') or tile.get('title')}**")
        ui.trend_chart(tile, key=f"{section_key}-{tile.get('metric_id')}-{filters['apartment']}")
        if tile.get("owner_caveat"):
            st.caption(tile["owner_caveat"])

    for tile in breakdown_tiles:
        rows = [v for k, v in (tile.get("value") or {}).items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if len(rows) < 2:
            continue
        st.markdown(f"**{tile.get('business_name') or tile.get('title')}**")
        ui.breakdown_chart(tile, key=f"{section_key}-{tile.get('metric_id')}")

    # The projection, estate-wide only. There is no apartment forecast, so under an apartment
    # filter it is omitted rather than shown as though it applied to the apartment.
    if section_key == "financial" and not filters["apartment"]:
        ui.forecast_panel(runtime.revenue_forecast())


def _movements(payload: dict) -> None:
    changes = payload.get("changes") or []
    if not changes:
        return
    ui.section_heading("What changed", count=len(changes),
                       note="Only complete months are compared, so a part-month is never "
                            "presented as a movement.")
    for change in changes:
        ui.movement_card(change)


def _findings(payload: dict) -> None:
    insights = payload.get("insights") or []
    if not insights:
        return
    ui.section_heading("What stands out", count=len(insights))
    for card in insights:
        ui.insight_card(card)


def _export(section_key: str, filters: dict, payload: dict) -> None:
    """The rows the server builds from the same authorized payload this page renders.

    Not a client-side dump of the screen: `export_section` runs after the role filter and after
    the gate, so a measure with no permitted headline exports its posture and its competing
    definitions and no number -- exactly as it appears above.
    """
    with st.expander("Export what is on screen"):
        if not st.button("Prepare export", key=f"export-{section_key}"):
            return
        rows = runtime.export_section(section_key, **filters)
        records = rows.get("rows") or []
        if not records:
            st.caption("There is nothing to export under the current filters.")
            return
        import csv
        import io
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
        st.download_button(
            "Download CSV", buffer.getvalue().encode("utf-8"),
            file_name=f"{section_key}.csv", mime="text/csv",
            key=f"download-{section_key}")


def _capabilities(payload: dict) -> None:
    capabilities = payload.get("capabilities") or {}
    limited = capabilities.get("limited") or []
    if not limited:
        return
    with st.expander("What this section cannot answer"):
        for item in limited:
            st.write(f"- **{item.get('label', '')}** — {item.get('limitation', '')}")
