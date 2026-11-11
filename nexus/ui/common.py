"""Reusable page chrome and data helpers."""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from nexus.config import ROOT
from nexus.services.dates import get_zone


def apply_theme() -> None:
    style = ROOT / "assets" / "styles" / "theme.css"
    if style.exists():
        st.markdown(f"<style>{style.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    settings = st.session_state.get("nexus_settings", {})
    zone_name = settings.get("timezone", "Asia/Kolkata")
    now = datetime.now(get_zone(zone_name))
    safe_title = escape(title)
    safe_subtitle = escape(subtitle)
    st.markdown(
        f'<div class="nexus-header"><div><div class="eyebrow">PERSONAL COMMAND CENTER</div>'
        f'<h1>{safe_title}</h1><div class="page-subtitle">{safe_subtitle}</div></div>'
        f'<div class="header-time"><span>{now.strftime("%A, %d %B %Y")}</span>'
        f'<strong>{now.strftime("%I:%M %p")}</strong><small>{escape(zone_name)}</small></div></div>',
        unsafe_allow_html=True,
    )


def section_title(title: str, caption: str | None = None) -> None:
    st.markdown(f'<div class="section-title">{escape(title)}</div>', unsafe_allow_html=True)
    if caption:
        st.caption(caption)


def empty_state(message: str, hint: str | None = None) -> None:
    st.markdown(f'<div class="empty-state"><div class="empty-mark">◈</div><strong>{escape(message)}</strong>'
                f'{f"<span>{escape(hint)}</span>" if hint else ""}</div>', unsafe_allow_html=True)


def show_table(rows: list[dict[str, Any]], *, height: int = 320) -> None:
    if not rows:
        empty_state("Nothing here yet", "Add a record to start building your history.")
        return
    frame = pd.DataFrame(rows)
    show_dataframe(frame, alt="Table of saved NEXUS records", height=height)


def show_dataframe(frame: pd.DataFrame, *, alt: str, height: int | str = "auto") -> None:
    st.dataframe(frame, hide_index=True, width="stretch", height=height, alt=alt)


def show_plotly(figure: Any, *, alt: str) -> None:
    st.plotly_chart(figure, width="stretch", alt=alt)


def records_frame(records: list[Any], columns: list[tuple[str, str]]) -> pd.DataFrame:
    rows = []
    for item in records:
        rows.append({label: _display_value(getattr(item, name, None)) for name, label in columns})
    return pd.DataFrame(rows)


def _display_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return value


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")

