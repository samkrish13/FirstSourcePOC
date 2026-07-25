"""Case Log — SQLite history for processed cases."""

from __future__ import annotations

import json

import streamlit as st

import db
from ui.shell import (
    BRANCH_LABELS,
    chrome,
    page_header,
    page_setup,
    rebuild_result_from_case,
)

page_setup("Case Log")
if not chrome("case_log"):
    st.stop()
page_header(
    "Case Log",
    "Persisted cases with status, assignment, actions, and messages.",
)

db.init_db()
cases = db.list_cases(limit=200)

if not cases:
    st.info("No cases yet. Sign in as an agent and run work from Process.")
else:
    st.dataframe(
        [
            {
                "When": (c.get("received_at") or c.get("created_at") or "")[:19],
                "Case": c.get("case_id"),
                "Status": db.STATUS_LABELS.get(c.get("status") or "open", c.get("status")),
                "Assignee": c.get("assigned_to") or "Unassigned",
                "SLA": db.sla_remaining(c.get("sla_due_at")),
                "Type": BRANCH_LABELS.get(c.get("request_type", ""), c.get("request_type")),
                "Account": c.get("account"),
                "Updated by": c.get("status_updated_by"),
                "Subject": c.get("subject"),
            }
            for c in cases
        ],
        width="stretch",
        hide_index=True,
        height=280,
    )

    case_ids = [c["case_id"] for c in cases]
    focus = st.session_state.get("case_log_focus")
    default_idx = case_ids.index(focus) if focus in case_ids else 0
    selected = st.selectbox("Inspect case", case_ids, index=default_idx)
    if selected:
        st.session_state.case_log_focus = selected

        if st.button("Replay on Process", type="primary", key=f"replay_{selected}"):
            rebuilt = rebuild_result_from_case(selected)
            if not rebuilt:
                st.error("Could not rebuild this case.")
            else:
                case = db.get_case(selected) or {}
                st.session_state.workspace_subject = case.get("subject") or ""
                st.session_state.workspace_body = case.get("body") or ""
                st.session_state.workspace_source_id = f"replay:{selected}"
                st.session_state.last_result = rebuilt
                st.switch_page("pages/0_Process.py")

        a_col, m_col = st.columns(2)
        with a_col:
            st.markdown("##### Actions")
            actions = db.get_case_actions(selected)
            st.dataframe(
                [
                    {
                        "Step": a.get("step_order"),
                        "When": a.get("created_at"),
                        "Action": a.get("action_type"),
                        "Detail": a.get("detail"),
                    }
                    for a in actions
                ],
                width="stretch",
                hide_index=True,
                height=280,
            )
            st.markdown("##### Action payloads")
            for a in actions:
                try:
                    payload = json.loads(a.get("payload_json") or "{}")
                except json.JSONDecodeError:
                    payload = {}
                if payload:
                    with st.expander(f"{a.get('step_order')} · {a.get('action_type')}"):
                        st.json(payload)
        with m_col:
            st.markdown("##### Messages")
            messages = db.get_case_messages(selected)
            for m in messages:
                with st.expander(
                    f"{m.get('direction')} · {m.get('channel')} · {m.get('created_at')}"
                ):
                    st.text(m.get("content") or "")
