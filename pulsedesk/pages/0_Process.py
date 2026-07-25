"""Process — work inbox + run workbench + linear result spine."""

from __future__ import annotations

import streamlit as st

import db
from integrations.gmail_inbox import (
    MAILBOX_ADDRESS,
    gmail_configured,
    sync_gmail_inbox,
)
from ui.shell import (
    BRANCH_LABELS,
    PLAYBOOKS,
    active_role,
    all_inbox_items,
    chrome,
    compose_new_request,
    current_user,
    filter_cases_by_query,
    open_branch_compare_dialog,
    open_case_in_workspace,
    open_in_workspace,
    page_header,
    page_setup,
    render_mail_case_list,
    render_playbook_rail,
    render_result_spine,
    seed_work_inbox_if_empty,
)
from workflows.pipeline import process_request

page_setup("Process")
if not chrome("process"):
    st.stop()

user = current_user() or {}
role = active_role()
seed_work_inbox_if_empty()

page_header(
    "Process" if role == "agent" else "Process · Tech Lead",
    (
        "Work inbox → claim or compose → run playbook → release or escalate with a reason."
        if role == "agent"
        else "Escalated queue — acknowledge, approve release, or return with a note the agent will see."
    ),
)

left, main = st.columns([1.25, 1.95], gap="medium")

with left:
    if role == "lead":
        escalated = db.list_escalated_cases(limit=40)
        q = st.text_input(
            "Search queue",
            placeholder="Search cases, subjects, accounts…",
            key="lead_inbox_search",
            label_visibility="collapsed",
        )
        escalated = filter_cases_by_query(escalated, q)
        focus = st.session_state.get("lead_queue_focus")
        ids = {c["case_id"] for c in escalated}
        if escalated and focus not in ids:
            focus = escalated[0]["case_id"]
            st.session_state.lead_queue_focus = focus

        clicked = render_mail_case_list(
            escalated,
            selected_id=focus,
            key_prefix="lead_mail",
            title="Escalated",
        )
        if clicked:
            if open_case_in_workspace(clicked):
                st.session_state.lead_queue_focus = clicked
                st.rerun()
        elif focus and focus != st.session_state.get("workspace_source_id"):
            if open_case_in_workspace(focus):
                st.rerun()

        if not escalated:
            st.caption("No escalated cases. Agents escalate Needs Review work to you.")

        render_playbook_rail(result=st.session_state.get("last_result"))

    else:
        filt = st.radio(
            "Assignment",
            ["Mine", "Unassigned", "All"],
            horizontal=True,
            key="inbox_filter",
        )
        me = user.get("username") or ""
        if filt == "Mine":
            inbox = db.list_inbox(assigned_to=me)
        elif filt == "Unassigned":
            inbox = db.list_inbox(unassigned_only=True)
        else:
            inbox = db.list_inbox()

        q = st.text_input(
            "Search inbox",
            placeholder="Search cases, subjects, accounts…",
            key="work_inbox_search",
            label_visibility="collapsed",
        )
        inbox = filter_cases_by_query(inbox, q)

        tool_a, tool_b, tool_c = st.columns(3)
        with tool_a:
            if st.button("Compose", width="stretch", type="primary", key="compose_new"):
                compose_new_request()
                st.rerun()
        with tool_b:
            if st.button(
                "Compare",
                width="stretch",
                key="open_branch_compare",
                help="Coach — compare how two playbook branches differ.",
            ):
                open_branch_compare_dialog()
        with tool_c:
            sync = st.button(
                "Sync Gmail",
                width="stretch",
                key="sync_gmail",
                help=f"Pull new mail from {MAILBOX_ADDRESS} into this inbox.",
            )
        st.caption(f"Linked mailbox · `{MAILBOX_ADDRESS}`")
        if sync:
            if not gmail_configured():
                st.warning(
                    "Add a Google **App Password** for "
                    f"`{MAILBOX_ADDRESS}` in `.streamlit/secrets.toml` "
                    "(see `.streamlit/secrets.toml.example`) or set "
                    "`GMAIL_APP_PASSWORD` in `.env`, then Sync again."
                )
            else:
                with st.spinner(f"Syncing {MAILBOX_ADDRESS}…"):
                    try:
                        report = sync_gmail_inbox(
                            limit=15,
                            actor=user.get("name") or "gmail-sync",
                        )
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Gmail sync failed: {exc}")
                        report = None
                if report:
                    n_new = len(report.get("created") or [])
                    n_skip = len(report.get("skipped") or [])
                    n_err = len(report.get("errors") or [])
                    st.success(
                        f"Synced **{report.get('fetched', 0)}** messages · "
                        f"**{n_new}** new cases · **{n_skip}** already in inbox"
                        + (f" · **{n_err}** errors" if n_err else "")
                    )
                    if report.get("errors"):
                        st.caption("; ".join(report["errors"][:3]))
                    if n_new:
                        st.rerun()

        focus = st.session_state.get("selected_inbox_id")
        ids = {c["case_id"] for c in inbox}
        if inbox and focus not in ids:
            focus = inbox[0]["case_id"]
            st.session_state.selected_inbox_id = focus

        clicked = render_mail_case_list(
            inbox,
            selected_id=focus,
            key_prefix="work_mail",
            title="Inbox",
        )
        if clicked:
            if open_case_in_workspace(clicked):
                st.rerun()
        elif focus and focus != st.session_state.get("workspace_source_id"):
            if open_case_in_workspace(focus):
                st.rerun()

        if focus and focus in ids:
            c_claim, c_rel = st.columns(2)
            with c_claim:
                if st.button("Claim", width="stretch", key="claim_case"):
                    db.assign_case(focus, me, updated_by=user.get("name"))
                    open_case_in_workspace(focus)
                    st.rerun()
            with c_rel:
                if st.button("Unassign", width="stretch", key="unassign_case"):
                    db.assign_case(focus, None, updated_by=user.get("name"))
                    st.rerun()
        elif not inbox:
            st.caption("No cases in this filter. Compose a request or switch filter.")

        with st.expander("Load demo sample into form", expanded=False):
            samples = all_inbox_items()
            sid = st.selectbox(
                "Sample",
                [s["id"] for s in samples],
                format_func=lambda i: next(
                    (
                        f"{s['id']} · {BRANCH_LABELS.get(s.get('branch', ''), s.get('branch'))}"
                        for s in samples
                        if s["id"] == i
                    ),
                    i,
                ),
            )
            if st.button("Load sample", key="load_demo_sample"):
                item = next(s for s in samples if s["id"] == sid)
                open_in_workspace(item)
                st.rerun()

        render_playbook_rail(result=st.session_state.get("last_result"))

with main:
    src_id = st.session_state.get("workspace_source_id") or "—"
    st.markdown(
        f'<div class="pd-rail-title">Active case · <span class="pd-mono">{src_id}</span></div>',
        unsafe_allow_html=True,
    )
    st.text_input("Subject", key="workspace_subject", disabled=role == "lead")
    st.text_area(
        "Message body",
        key="workspace_body",
        height=180,
        disabled=role == "lead",
    )

    if role == "agent":
        with st.expander("Upload request file (optional)", expanded=False):
            uploaded = st.file_uploader(
                "Accepts .txt / .eml",
                type=["txt", "eml", "text"],
                key="request_upload",
            )
            if uploaded is not None and st.button("Load upload into form", key="apply_upload"):
                raw = uploaded.read().decode("utf-8", errors="replace")
                lines = raw.splitlines()
                subj = ""
                body_lines: list[str] = []
                for i, line in enumerate(lines):
                    if line.lower().startswith("subject:"):
                        subj = line.split(":", 1)[1].strip()
                    elif i == 0 and not subj and len(line) < 160:
                        subj = line.strip()
                    else:
                        body_lines.append(line)
                st.session_state.workspace_subject = subj or uploaded.name
                st.session_state.workspace_body = "\n".join(body_lines).strip() or raw
                st.session_state.workspace_source_id = f"upload:{uploaded.name}"
                st.session_state.last_result = None
                st.rerun()

        force_options = ["(auto)"] + [key for key, *_ in PLAYBOOKS]
        force_pick = st.selectbox(
            "DEMO ONLY — force playbook override",
            force_options,
            key="force_branch",
        )

        run = st.button("Run playbook", type="primary", width="stretch")
        if run or bool(st.session_state.pop("auto_run", False)):
            subject = (st.session_state.workspace_subject or "").strip() or "(no subject)"
            body = (st.session_state.workspace_body or "").strip()
            if not body:
                st.warning("Message body is required.")
            else:
                force_type = None if force_pick == "(auto)" else force_pick
                with st.spinner("Running playbook…"):
                    st.session_state.last_result = process_request(
                        subject,
                        body,
                        force_type=force_type,
                        assigned_to=user.get("username"),
                        actor=user.get("name"),
                    )
                st.session_state.workspace_source_id = st.session_state.last_result.get(
                    "case_id"
                )
                st.session_state.selected_inbox_id = st.session_state.workspace_source_id
                st.rerun()

    result = st.session_state.get("last_result")
    if result:
        st.markdown("---")
        render_result_spine(result)
    elif role == "lead":
        st.caption("Select an escalated case from the left queue.")
    else:
        st.caption("Open a case from the inbox, or compose and Run playbook.")
