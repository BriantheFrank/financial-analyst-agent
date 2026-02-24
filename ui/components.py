from __future__ import annotations

from contextlib import contextmanager

import streamlit as st

from ui.theme import PALETTE


@contextmanager
def card(title: str | None = None, caption: str | None = None):
    st.markdown("<div class='ui-card'>", unsafe_allow_html=True)
    if title:
        st.markdown(f"### {title}")
    if caption:
        st.caption(caption)
    try:
        yield
    finally:
        st.markdown("</div>", unsafe_allow_html=True)


def metric_card(
    label: str,
    value: str,
    delta: str | None = None,
    delta_color: str = "normal",
    help_text: str | None = None,
    icon: str | None = None,
) -> None:
    title = f"{icon} {label}" if icon else label
    st.metric(label=title, value=value, delta=delta, delta_color=delta_color, help=help_text)


def status_pill(status: str) -> None:
    status_map = {
        "Ready": PALETTE["accent_sky"],
        "Fetching": PALETTE["warning"],
        "Complete": PALETTE["positive"],
        "Error": PALETTE["negative"],
    }
    color = status_map.get(status, PALETTE["body"])
    st.markdown(f"<span class='status-pill' style='background:{color};'>{status}</span>", unsafe_allow_html=True)
