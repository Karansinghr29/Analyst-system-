"""
analyst.py -- the AI Business Analyst.

There is no AI here. This page collects a question, hands it to `AnalyticsService.ask` -- the same
pipeline the API and every other surface calls -- and renders what comes back.

What that pipeline does, restated because this page must never appear to do it: the deterministic
engine answers the question, and a language model, WHERE ONE IS CONFIGURED, re-words the finished
answer under the existing verbalization guard. The model never computes a figure, chooses a
definition, moves a posture or names a metric the engine did not. With no model configured the
same answer arrives in the engine's own wording, which is a complete answer and not a degraded
one.
"""
from __future__ import annotations

import streamlit as st

from owner_app import runtime, ui

SUGGESTIONS = (
    "How is the business doing?",
    "What changed this month?",
    "What should I do?",
    "What are our biggest business risks?",
    "Which numbers should I trust?",
    "Which definition should we use?",
)


def render() -> None:
    st.title("AI Business Analyst")
    st.caption("Ask in your own words. Every figure in the answer is produced by the analytics "
               "engine; the wording is the only thing a language model touches.")

    if "analyst_history" not in st.session_state:
        st.session_state.analyst_history = []
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = None

    st.markdown("##### Suggested questions")
    columns = st.columns(3)
    for index, suggestion in enumerate(SUGGESTIONS):
        if columns[index % 3].button(suggestion, key=f"suggest-{index}",
                                     use_container_width=True):
            _ask(suggestion)

    typed = st.chat_input("Ask about your business")
    if typed:
        _ask(typed)

    for question, answer in reversed(st.session_state.analyst_history):
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            _answer(answer)


def _ask(question: str) -> None:
    with st.spinner("Working through the evidence..."):
        try:
            result = runtime.ask(question, st.session_state.conversation_id)
        except Exception as exc:                       # pragma: no cover - surfaced to the owner
            st.error(f"The question could not be answered: {type(exc).__name__}")
            return
    st.session_state.conversation_id = result.get("conversation_id")
    st.session_state.analyst_history.append((question, result))


def _answer(result: dict) -> None:
    """The answer as the engine finished it.

    The trust posture is shown in the owner's words. `headline_permitted` is the gate's: where it
    is false the answer carries no single figure, and this page adds none.
    """
    for line in str(result.get("answer", "")).split("\n"):
        if line.strip():
            st.write(line.strip())

    if not result.get("headline_permitted", True):
        st.caption("No single figure is stated for this: the records hold more than one "
                   "defensible answer, and all of them are in the answer above.")

    for limitation in result.get("limitations") or []:
        st.caption(f"⚠️ {limitation}")

    if result.get("llm_fallback"):
        st.caption("The wording here is the engine's own: the language model was unavailable, "
                   "so the answer was not re-worded. The figures are unaffected.")

    # The audit trail the answer was built from. Identifiers belong here, not above.
    ui.technical_panel("Evidence & technical details", {
        "Measures used": result.get("metric_ids"),
        "Trust level": result.get("trust_level"),
        "Evidence chain": result.get("evidence_chain"),
        "Guard violations": result.get("guard_violations"),
        "Conversation": result.get("conversation_id"),
    })
