"""
ui.py -- how an owner-safe payload is drawn. Presentation only.

Every function here takes a projection the engine already built and renders it. None of them
computes a figure, decides a posture, orders competing definitions by preference, or derives a
label from a trust level. Where a string appears on screen, the engine wrote it.

TWO RULES THIS MODULE ENFORCES
------------------------------

1. The owner's default view carries no machine vocabulary. Metric identifiers, database object
   names, conflict and finding record ids, trust tokens and file names stay out of it. The
   payloads already carry an owner-safe field beside each technical one -- `business_name` beside
   `title`, `owner_status` beside `trust_level`, `owner_what` beside `issue` -- and this module
   reads the owner-safe one. Where a surface genuinely needs the technical record, it goes inside
   an explicitly expanded panel, which is where the existing product already puts it.

2. A measure is drawn as its posture, never as a number the posture forbids. A permitted headline
   shows its figure; a conflicted measure shows every competing definition and no headline; a
   blocked one shows the engine's unavailable statement. `headline_permitted` decides, and it is
   the gate's, not this file's.
"""
from __future__ import annotations

import streamlit as st

# The five owner-facing postures, and the visual weight each carries. The mapping from a trust
# level to its owner phrase lives in the engine (`owner_semantics.OWNER_TRUST_STATUS`) and arrives
# on the payload as `owner_status`; this only decides which colour a chip is drawn in, keyed on
# the phrase the engine chose rather than on the level behind it.
_TONE_ICON = {
    "neutral": "🟢",
    "caution": "🟡",
    "conflict": "🟠",
    "unavailable": "⚪",
}


def trust_chip(trust: dict | None) -> str:
    """The owner's word for a posture, with a tone marker. Never the canonical level."""
    if not trust:
        return ""
    status = trust.get("owner_status") or trust.get("badge") or "Cannot be determined"
    return f"{_TONE_ICON.get(trust.get('tone'), '⚪')} {status}"


def as_of_line(payload: dict) -> None:
    if payload.get("as_of"):
        st.caption(f"As at {payload['as_of']}")


def section_heading(title: str, note: str = "", count: int | None = None) -> None:
    st.subheader(title if count is None else f"{title} · {count}")
    if note:
        st.caption(note)


# --- measures -----------------------------------------------------------------------------------

def metric_tile(tile: dict, *, key_prefix: str = "") -> None:
    """One measure, drawn as the posture the gate gave it.

    The three branches below are the product's existing rule, not a new one: a permitted headline,
    otherwise the competing definitions in full, otherwise the engine's own statement that nothing
    can be stated. Nothing here can produce a figure for a measure the gate refused one for,
    because no branch reads `value` unless `headline_permitted` is true.
    """
    name = tile.get("business_name") or tile.get("title") or ""
    with st.container(border=True):
        st.markdown(f"**{name}**")
        st.caption(trust_chip(tile.get("trust")))

        if tile.get("headline_permitted") and tile.get("display_value"):
            # `display_parts` is the engine's own naming of a composite value's parts. A
            # single-figure measure carries none, and its formatted figure is the headline.
            parts = tile.get("display_parts") or []
            if parts:
                for part in parts:
                    st.markdown(f"**{part.get('label', '')}** — {part.get('value', '')}")
            else:
                st.markdown(f"### {tile['display_value']}")

        elif tile.get("definitions"):
            # A conflicted measure. Every definition, in the engine's order, each with its own
            # figure. No default, no average, and no ordering that implies a preference.
            st.caption(tile.get("posture_line") or (tile.get("trust") or {}).get("owner_label", ""))
            for label, value, parts in _definitions(tile):
                if parts:
                    st.markdown(f"- **{label}**")
                    for part in parts:
                        st.caption(f"    {part.get('label', '')} — {part.get('value', '')}")
                else:
                    st.markdown(f"- **{label}** — {value}" if value else f"- **{label}**")

        else:
            st.caption((tile.get("trust") or {}).get("owner_label", ""))
            statement = tile.get("owner_unavailable") or ""
            if statement:
                st.write(statement)

        caveat = tile.get("owner_caveat") or ""
        if caveat:
            st.caption(f"⚠️ {caveat}")


def _definitions(tile: dict):
    """Every competing definition as (label, figure, parts).

    `owner_definitions` is the engine's own projection -- labels stated as the business
    distinction each definition draws, and composite values named part by part -- and is what
    this reads. The raw `definitions` list is the fallback for a payload that predates it, and
    arrives in one of two shapes depending on the endpoint: the dashboard payload flattens the
    dataclass to [label, value, display_value], the section payload uses the tile's own
    `as_dict` and gives {"label": ..., "display_value": ...}. Reading either is presentation
    adaptation; nothing here reorders, drops or prefers a definition.
    """
    owner = tile.get("owner_definitions")
    if owner:
        return [(d.get("label", ""), d.get("value", ""), d.get("parts") or []) for d in owner]

    out = []
    for definition in tile.get("definitions") or []:
        if isinstance(definition, dict):
            out.append((definition.get("label", ""),
                        definition.get("display_value") or "", []))
        elif isinstance(definition, (list, tuple)) and definition:
            out.append((definition[0],
                        definition[2] if len(definition) > 2 else "", []))
    return out


def tile_grid(tiles: list, columns: int = 3, key_prefix: str = "") -> None:
    if not tiles:
        return
    for row_start in range(0, len(tiles), columns):
        row = tiles[row_start:row_start + columns]
        for column, tile in zip(st.columns(len(row)), row):
            with column:
                metric_tile(tile, key_prefix=key_prefix)


# --- movements ----------------------------------------------------------------------------------

def movement_card(change: dict) -> None:
    """A validated period movement.

    Direction and both figures, all formatted by the engine. The direction word is the engine's
    ("rose", "fell"); nothing here calls a movement good, bad, large or small, because the
    evidence fixes no threshold for any of those.
    """
    with st.container(border=True):
        st.markdown(f"**{change.get('title', '')}**")
        line = change.get("direction", "")
        if change.get("display_change"):
            line = f"{line} by {change['display_change']}"
        st.write(line)
        if change.get("previous_period") and change.get("current_period"):
            st.caption(f"{change['previous_period']} → {change['current_period']}")

        if change.get("current_display") and change.get("previous_display"):
            left, middle, right = st.columns(3)
            left.metric(change.get("current_period", "Current"), change["current_display"])
            middle.metric(change.get("previous_period", "Previous"), change["previous_display"])
            delta = change.get("absolute_display", "")
            if change.get("percent_display"):
                delta = f"{delta} ({change['percent_display']})"
            right.metric("Change", delta or "—")

        # The decomposition, only where the engine reconciled the parts to the whole exactly.
        # `component_note` says so when it did not, and then no parts are drawn.
        if change.get("components"):
            with st.expander("What moved inside it"):
                if change.get("component_basis"):
                    st.caption(change["component_basis"])
                for component in change["components"]:
                    st.write(f"- {component.get('label', '')}: "
                             f"{component.get('display_change', '')} "
                             f"({component.get('direction', '')})")
                if change.get("component_note"):
                    st.caption(change["component_note"])
        elif change.get("component_note"):
            st.caption(change["component_note"])

        for note_field in ("unavailable_reason", "coverage_note", "partial_note",
                           "alternative_note"):
            if change.get(note_field):
                st.caption(change[note_field])


# --- findings -----------------------------------------------------------------------------------

def insight_card(card: dict) -> None:
    """A finding, in the order an owner reads one: what, why, what to do."""
    with st.container(border=True):
        heading = card.get("action_category_label") or card.get("category_label") or ""
        st.caption(f"{heading} · {trust_chip(card.get('trust'))}")
        if card.get("what_happened"):
            st.markdown(f"**{card['what_happened']}**")
        if card.get("why_it_matters"):
            st.write(card["why_it_matters"])
        if card.get("recommended_action"):
            st.info(card["recommended_action"])


def subject_card(group: dict) -> None:
    """One business subject and the findings behind it.

    Grouped so a subject the records raise four separate findings about is one thing to deal
    with, not four. Every member finding is listed, so grouping hides nothing.
    """
    with st.container(border=True):
        top, right = st.columns([4, 1])
        top.markdown(f"**{group.get('subject', '')}**")
        right.caption(group.get("action_category_label", ""))
        for item in group.get("items", []):
            if item.get("what_happened"):
                st.write(f"• {item['what_happened']}")
            if item.get("recommended_action"):
                st.caption(f"  → {item['recommended_action']}")


# --- series -------------------------------------------------------------------------------------

def month_series(tile: dict):
    """The recorded months a measure carries, as (period, value) pairs.

    Reads the engine's value dictionary and sorts by period. That is ordering, not arithmetic:
    no point is interpolated, aggregated, converted or filled, and a month the records do not
    hold stays absent rather than becoming a zero.
    """
    value = tile.get("value")
    if not isinstance(value, dict):
        return []
    keys = [k for k in value if isinstance(k, str) and len(k) >= 7 and k[:4].isdigit()
            and k[4] == "-"]
    if not keys:
        return []
    return [(k, value[k]) for k in sorted(keys)
            if isinstance(value[k], (int, float)) and not isinstance(value[k], bool)]


def trend_chart(tile: dict, *, recent_months: int = 24, key: str = "") -> None:
    """A recorded series, drawn.

    Charting only. The points are the engine's, the labels beside them are the engine's formatted
    strings, and the "recent" view is a slice of the same list -- not a resampling.
    """
    points = month_series(tile)
    if len(points) < 2:
        return

    name = tile.get("business_name") or tile.get("title") or "Series"
    show_all = st.toggle(
        f"Full recorded history ({len(points)} months)",
        key=f"range-{key}",
        value=False,
        help="Off shows the most recent months. Either way, every point is a recorded month.",
    )
    shown = points if show_all else points[-recent_months:]

    try:
        import pandas as pd
        frame = pd.DataFrame({name: [p[1] for p in shown]},
                             index=[p[0] for p in shown])
        st.line_chart(frame, height=220)
    except Exception:
        st.caption("This series cannot be drawn here; the recorded figures are below.")

    displays = tile.get("series_display") or {}
    latest_period, _ = shown[-1]
    if displays.get(latest_period):
        st.caption(f"Latest recorded month {latest_period}: {displays[latest_period]}")


def breakdown_chart(tile: dict, *, key: str = "") -> None:
    """A flat named breakdown, drawn as bars. Categories and figures are the engine's."""
    value = tile.get("value")
    if not isinstance(value, dict):
        return
    rows = {k.replace("_", " ").capitalize(): v for k, v in value.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
            and not (len(k) >= 7 and k[:4].isdigit() and k[4] == "-")}
    if len(rows) < 2:
        return
    try:
        import pandas as pd
        st.bar_chart(pd.DataFrame({"": list(rows.values())}, index=list(rows.keys())),
                     height=220)
    except Exception:
        for label, figure in rows.items():
            st.write(f"- {label}: {figure}")


# --- forecast -----------------------------------------------------------------------------------

def forecast_panel(forecast: dict | None) -> None:
    """The engine's projection, kept visually apart from anything recorded.

    Drawn as text, deliberately: the forecaster produced a statement with its own interval and
    tested error, and re-plotting it beside the recorded line would invite the two to be read as
    one series. Nothing below has happened yet, and the panel says so before it says anything
    else.
    """
    if not forecast:
        return
    with st.container(border=True):
        st.markdown("**Projected — not recorded**")
        st.caption("A projection of the recorded trend. Nothing below has happened yet, and "
                   "none of it is a recorded figure.")
        for line in str(forecast.get("answer", "")).split("\n"):
            if line.strip():
                st.write(line.strip())
        for limitation in forecast.get("limitations") or []:
            st.caption(limitation)


# --- limitations and the technical record ---------------------------------------------------------

def limitations(items) -> None:
    if not items:
        return
    with st.expander("Caveats that apply to this page"):
        for item in items:
            st.write(f"- {item}")


def technical_panel(label: str, rows: dict) -> None:
    """The machine's own vocabulary, behind an explicit expander.

    This is the one place identifiers, object names and canonical trust levels belong. They are
    not removed from the product -- an owner who wants to see the record can -- they are simply
    not the default view.
    """
    populated = {k: v for k, v in rows.items() if v not in (None, "", [], {}, ())}
    if not populated:
        return
    with st.expander(label):
        for key, value in populated.items():
            if isinstance(value, (list, tuple)):
                value = ", ".join(str(v) for v in value)
            elif isinstance(value, dict):
                value = "; ".join(f"{k}: {v}" for k, v in value.items())
            st.write(f"**{key}** — {value}")
