"""PulseDesk entry — Process / Case Log / Playbooks workbench."""

from __future__ import annotations

import streamlit as st

import db

st.set_page_config(
    page_title="PulseDesk",
    page_icon="▣",
    layout="wide",
    # Desktop CSS pins the nav open; mobile starts collapsed so content isn't covered.
    initial_sidebar_state="auto",
)

# Cloud-safe: ensure SQLite schema exists before any page runs
db.init_db()

process = st.Page("pages/0_Process.py", title="Process", default=True)
case_log = st.Page("pages/1_Case_Log.py", title="Case Log")
playbooks = st.Page("pages/2_Playbooks.py", title="Playbooks")

nav = st.navigation([process, case_log, playbooks], position="hidden")
nav.run()
