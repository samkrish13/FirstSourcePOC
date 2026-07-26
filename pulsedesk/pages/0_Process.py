"""Process — work inbox + run workbench + linear result spine."""

from __future__ import annotations

import html

import streamlit as st

import db
from integrations.gmail_inbox import (
    gmail_configured,
    list_mailboxes,
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
    render_mailbox_connect_panel,
    render_playbook_rail,
    render_result_spine,
    clear_draft_keys,
    seed_work_inbox_if_empty,
    workspace_needs_case_reload,
)
from workflows.pipeline import process_request

# Active work — hide released from Mine / Unassigned
_WORK_STATUSES = [
    db.STATUS_OPEN,
    db.STATUS_ON_HOLD,
    db.STATUS_ESCALATED,
    db.STATUS_RETURNED,
]


def _is_composing() -> bool:
    src = str(st.session_state.get("workspace_source_id") or "")
    return src.startswith("manual:") or src.startswith("upload:")


page_setup("Process")
if not chrome("process"):
    st.stop()

user = current_user() or {}
role = active_role()
seed_work_inbox_if_empty()

# Apply queued subject/body BEFORE any widgets (inbox open / upload / compose)
pending = st.session_state.pop("_pending_workspace", None)
if isinstance(pending, dict):
    st.session_state.workspace_subject = str(pending.get("subject") or "")
    st.session_state.workspace_body = str(pending.get("body") or "")
    st.session_state.workspace_source_id = str(pending.get("source_id") or "")
    st.session_state.selected_inbox_id = pending.get("selected_inbox_id")
    if "last_result" in pending:
        st.session_state.last_result = pending.get("last_result")

page_header(
    "Process" if role == "agent" else "Process · Tech Lead",
    (
        "Pick a case from the inbox, run the playbook, then release or escalate."
        if role == "agent"
        else "Review escalated cases — acknowledge, approve release, or return to the agent."
    ),
    eyebrow="Workbench",
)

st.markdown(
    '<div class="pd-split-desk" aria-hidden="true"></div>',
    unsafe_allow_html=True,
)

# Inbox scrolls independently; workbench is NOT height-locked so Subject/Body/Draft
# text_areas keep their normal white Streamlit boxes (height panes squash them to 0).
_PANE_H = 860
_left_col, _main_col = st.columns([1.15, 1.85], gap="medium")
left = _left_col.container(height=_PANE_H, border=False)
main = _main_col

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
        searching = bool((q or "").strip())
        if searching:
            st.caption(f"{len(escalated)} match{'es' if len(escalated) != 1 else ''}")
        focus = st.session_state.get("lead_queue_focus")
        ids = {c["case_id"] for c in escalated}
        if (
            not searching
            and escalated
            and focus not in ids
            and not _is_composing()
        ):
            focus = escalated[0]["case_id"]
            st.session_state.lead_queue_focus = focus

        actions = render_mail_case_list(
            escalated,
            selected_id=None if _is_composing() or (searching and focus not in ids) else focus,
            key_prefix="lead_mail",
            title="Escalated",
        )
        if actions.get("open"):
            if open_case_in_workspace(str(actions["open"])):
                st.session_state.lead_queue_focus = actions["open"]
                st.rerun()
        elif (
            focus
            and not _is_composing()
            and not searching
            and workspace_needs_case_reload(focus)
        ):
            if open_case_in_workspace(str(focus)):
                st.session_state.lead_queue_focus = focus
                st.rerun()

        if not escalated:
            st.markdown(
                """
<div class="pd-empty">
  <div class="pd-empty-title">No escalated cases</div>
  <div class="pd-empty-hint">
    This lead queue only shows cases an agent has escalated.
    Sign out → sign in as agent (<code>p.sharma</code> / <code>agent</code>) to sync Gmail,
    run playbooks, then <strong>Escalate to lead</strong>. Those cases appear here.
  </div>
</div>
                """,
                unsafe_allow_html=True,
            )

        render_playbook_rail(result=st.session_state.get("last_result"))

    else:
        # Init before widget — do not pass default= when also writing session_state
        if "inbox_filter" not in st.session_state:
            st.session_state.inbox_filter = "Mine"
        pending_filt = st.session_state.pop("_pending_inbox_filter", None)
        if pending_filt in ("Mine", "Unassigned", "All"):
            st.session_state.inbox_filter = pending_filt
        pending_mailbox = st.session_state.pop("_pending_mailbox_view", None)
        if pending_mailbox:
            st.session_state.mailbox_view_filter = pending_mailbox

        filt = st.segmented_control(
            "Assignment",
            options=["Mine", "Unassigned", "All"],
            key="inbox_filter",
        ) or "Mine"
        me = user.get("username") or ""
        mailboxes = list_mailboxes()
        mailbox_ids = [m["id"] for m in mailboxes]
        mailbox_labels = {
            m["id"]: f"{m['label']} · {m['address']}" for m in mailboxes
        }

        # Filter which linked inbox to view (All = every case)
        known_sources = db.list_source_mailboxes()
        view_options = ["All mailboxes"] + known_sources
        if mailboxes:
            for m in mailboxes:
                if m["address"] not in view_options:
                    view_options.append(m["address"])
        mailbox_view = st.selectbox(
            "Show cases from",
            view_options,
            key="mailbox_view_filter",
        )
        source_filter = None if mailbox_view == "All mailboxes" else mailbox_view

        if filt == "Mine":
            # Mine first (all mailboxes), then optionally narrow — keep untagged
            # compose/demo cases visible when a Gmail filter is selected.
            inbox = db.list_inbox(assigned_to=me, statuses=_WORK_STATUSES)
            if source_filter:
                inbox = [
                    c
                    for c in inbox
                    if (c.get("source_mailbox") or "") in ("", source_filter)
                ]
        elif filt == "Unassigned":
            inbox = db.list_inbox(
                unassigned_only=True,
                statuses=_WORK_STATUSES,
                source_mailbox=source_filter,
            )
        else:
            # Active desk: hide Released so "All" doesn't look like open work
            inbox = db.list_inbox(
                statuses=_WORK_STATUSES, source_mailbox=source_filter
            )

        q = st.text_input(
            "Search inbox",
            placeholder="Search cases, subjects, accounts…",
            key="work_inbox_search",
            label_visibility="collapsed",
        )
        inbox = filter_cases_by_query(inbox, q)
        searching = bool((q or "").strip())
        if searching:
            st.caption(f"{len(inbox)} match{'es' if len(inbox) != 1 else ''}")

        tool_a, tool_b = st.columns(2)
        with tool_a:
            if st.button("Compose", width="stretch", type="primary", key="compose_new"):
                compose_new_request()
                st.session_state.selected_inbox_id = None
                st.rerun()
        with tool_b:
            if st.button(
                "Compare",
                width="stretch",
                key="open_branch_compare",
                help="Coach — compare how two playbook branches differ.",
            ):
                open_branch_compare_dialog()

        # One control: pick mailbox + sync
        # `_sync_busy` only disables across runs; clear leftovers from interrupted syncs
        st.session_state._sync_busy = False
        sync = False
        sync_pick = None
        if mailboxes:
            pick_col, sync_col = st.columns([2.4, 1.0], vertical_alignment="bottom")
            with pick_col:
                sync_pick = st.selectbox(
                    "Sync Gmail",
                    mailbox_ids,
                    format_func=lambda i: mailbox_labels.get(i, i),
                    key="sync_mailbox_pick",
                    help="Choose which linked mailbox to pull into this inbox.",
                )
            with sync_col:
                sync = st.button(
                    "Sync",
                    width="stretch",
                    key="sync_gmail",
                    help="Pull recent mail from the mailbox on the left.",
                )
            if len(mailboxes) == 1:
                st.caption(f"Linked · `{mailboxes[0]['address']}`")
            else:
                st.caption(f"{len(mailboxes)} mailboxes linked — pick one, then Sync.")
        else:
            st.caption(
                "No connected mailbox yet — open **Connect / manage mailboxes** below, "
                "send an invite, then paste the Google App Password."
            )

        # Keep Connect near Sync (not buried under the case list)
        st.markdown("##### Mailboxes")
        with st.expander(
            "Connect / manage mailboxes",
            expanded=(
                not mailboxes
                or st.session_state.get("side_panel_action") == "mailbox"
            ),
        ):
            render_mailbox_connect_panel(actor=user.get("name"))

        if sync:
            if not gmail_configured() or not sync_pick:
                st.warning(
                    "Connect a mailbox first: **Connect / manage mailboxes** → "
                    "Send invitation → paste App Password → Verify & connect."
                )
            else:
                label = mailbox_labels.get(sync_pick, sync_pick)
                with st.spinner(f"Syncing {label}…"):
                    try:
                        report = sync_gmail_inbox(
                            mailbox_id=sync_pick,
                            limit=15,
                            actor=user.get("name") or "gmail-sync",
                            assigned_to=me or None,
                        )
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Gmail sync failed: {exc}")
                        report = None
                if report:
                    n_new = len(report.get("created") or [])
                    n_skip = len(report.get("skipped") or [])
                    n_del = len(report.get("deleted") or [])
                    n_err = len(report.get("errors") or [])
                    mb_addr = str(report.get("mailbox") or "")
                    # New mail is assigned to you → Mine. Older synced mail is often
                    # Unassigned — land there so the list isn't empty after Sync.
                    if n_new:
                        st.session_state._pending_inbox_filter = "Mine"
                    elif n_skip or n_del:
                        st.session_state._pending_inbox_filter = "Unassigned"
                    if mb_addr:
                        st.session_state._pending_mailbox_view = mb_addr
                    # If the open case was pruned from Gmail, clear the workbench
                    open_id = str(st.session_state.get("workspace_source_id") or "")
                    if open_id and open_id in (report.get("deleted") or []):
                        st.session_state._pending_workspace = {
                            "subject": "",
                            "body": "",
                            "source_id": "",
                            "selected_inbox_id": None,
                            "last_result": None,
                        }
                    st.success(
                        f"**{report.get('label') or mb_addr}** · "
                        f"synced **{report.get('fetched', 0)}** · "
                        f"**{n_new}** new · **{n_skip}** already in inbox"
                        + (f" · **{n_del}** removed (deleted in Gmail)" if n_del else "")
                        + (f" · **{n_err}** errors" if n_err else "")
                        + (
                            " · showing **Mine**"
                            if n_new
                            else " · showing **Unassigned**"
                            if (n_skip or n_del)
                            else ""
                        )
                    )
                    if report.get("errors"):
                        st.caption("; ".join(report["errors"][:3]))
                    st.rerun()

        composing = _is_composing()
        focus = st.session_state.get("selected_inbox_id")
        ids = {c["case_id"] for c in inbox}
        suppress_focus = bool(st.session_state.pop("_suppress_inbox_autofocus", False))
        src_case = str(st.session_state.get("workspace_source_id") or "").strip()
        src_is_case = bool(
            src_case and not src_case.startswith(("manual:", "upload:", "replay:"))
        )
        # While searching: never autofocus / reload — that steals the search box caret
        # After Run playbook: never jump to another inbox card over the new result
        if (
            not searching
            and not suppress_focus
            and inbox
            and focus not in ids
            and not composing
        ):
            if src_is_case and src_case not in ids:
                # Keep workbench on the case we just ran (may be outside current filter)
                focus = src_case
                st.session_state.selected_inbox_id = src_case
            else:
                focus = inbox[0]["case_id"]
                st.session_state.selected_inbox_id = focus

        actions = render_mail_case_list(
            inbox,
            selected_id=None
            if composing or (searching and focus not in ids)
            else (focus if focus in ids else None),
            key_prefix="work_mail",
            title="Inbox",
            allow_claim=True,
            claim_username=me,
            assignment_view=filt,
        )
        if actions.get("open"):
            cid = str(actions["open"])
            st.session_state.selected_inbox_id = cid
            if open_case_in_workspace(cid):
                st.rerun()
            else:
                st.error(f"Could not load case `{cid}` into the workbench.")
        if actions.get("claim"):
            if not st.session_state.get("_claim_busy"):
                st.session_state._claim_busy = True
                try:
                    cid = str(actions["claim"])
                    db.assign_case(cid, me, updated_by=user.get("name"))
                    st.session_state._pending_inbox_filter = "Mine"
                    st.session_state.selected_inbox_id = cid
                    if not open_case_in_workspace(cid):
                        st.error(f"Claimed `{cid}` but could not load it.")
                    else:
                        st.toast(f"Claimed {cid} — now in Mine")
                finally:
                    st.session_state._claim_busy = False
                st.rerun()
        if actions.get("unassign"):
            if not st.session_state.get("_unassign_busy"):
                st.session_state._unassign_busy = True
                try:
                    cid = str(actions["unassign"])
                    db.assign_case(cid, None, updated_by=user.get("name"))
                    st.session_state._pending_inbox_filter = "Unassigned"
                    st.toast(f"Unassigned {cid}")
                finally:
                    st.session_state._unassign_busy = False
                st.rerun()
        if (
            focus
            and focus in ids
            and not composing
            and not searching
            and workspace_needs_case_reload(focus)
        ):
            if open_case_in_workspace(focus):
                st.rerun()

        if not inbox:
            hint = (
                "No cases match this search — clear the search box."
                if searching
                else (
                    "Synced Gmail usually lands in **Unassigned** until you Claim it. "
                    "Try Unassigned / All, or clear the mailbox filter to All mailboxes."
                )
            )
            st.markdown(
                f"""
<div class="pd-empty">
  <div class="pd-empty-title">{"No matches" if searching else "No cases in this filter"}</div>
  <div class="pd-empty-hint">{hint}</div>
</div>
                """,
                unsafe_allow_html=True,
            )

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
                key="demo_sample_pick",
            )
            if st.button("Load sample", key="load_demo_sample"):
                item = next(s for s in samples if s["id"] == sid)
                open_in_workspace(item)
                st.rerun()

        render_playbook_rail(result=st.session_state.get("last_result"))

with main:
    # Release success when desk was cleared (no spine on screen)
    release_flash = st.session_state.get("_release_flash")
    if (
        isinstance(release_flash, dict)
        and release_flash.get("show_empty")
        and not st.session_state.get("last_result")
    ):
        flash = st.session_state.pop("_release_flash", None) or {}
        cid = flash.get("case_id") or ""
        if flash.get("sent"):
            st.success(
                f"**Case closed** `{cid}` — email sent. "
                f"{flash.get('detail') or ''} Reopen from Case Log → Replay."
            )
        else:
            st.success(
                f"**Case closed** `{cid}` — "
                f"{flash.get('detail') or 'Removed from active inbox.'} "
                "Reopen from Case Log → Replay on Process."
            )

    src_id = str(st.session_state.get("workspace_source_id") or "").strip()
    banner_case = None
    replay_id = ""
    if src_id.startswith("replay:"):
        replay_id = src_id.split(":", 1)[1].strip()
        if replay_id:
            banner_case = db.get_case(replay_id)
    elif src_id and not src_id.startswith(("manual:", "upload:")):
        banner_case = db.get_case(src_id)

    case_closed = bool(
        banner_case and str(banner_case.get("status") or "") == db.STATUS_RELEASED
    )

    if banner_case:
        status = str(banner_case.get("status") or "")
        status_label = db.STATUS_LABELS.get(status, status or "—")
        assignee = str(banner_case.get("assigned_to") or "").strip()
        if assignee and assignee == (user.get("username") or ""):
            assign_label = "Assigned to you"
        elif assignee:
            assign_label = f"Assigned to {assignee}"
        else:
            assign_label = "Unassigned"
        subject = (
            st.session_state.get("workspace_subject")
            or banner_case.get("subject")
            or "Untitled request"
        )
        closed = status == db.STATUS_RELEASED
        if replay_id and closed:
            eyebrow = "Closed · Replay from Case Log"
        elif replay_id:
            eyebrow = "Replay from Case Log"
        elif closed:
            eyebrow = "Closed"
        else:
            eyebrow = "Open in workbench"
        banner_cls = "pd-case-banner released" if closed else "pd-case-banner"
        display_id = replay_id or src_id
        st.markdown(
            f"""
<div class="{banner_cls}">
  <div class="eyebrow">{html.escape(eyebrow)}</div>
  <div class="case-id">{html.escape(display_id)}</div>
  <div class="subject">{html.escape(str(subject))}</div>
  <div class="meta">
    <span><strong>{html.escape(str(status_label))}</strong></span>
    <span>{html.escape(assign_label)}</span>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )
    elif src_id:
        draft_subj = st.session_state.get("workspace_subject") or "Draft request"
        st.markdown(
            f"""
<div class="pd-case-banner">
  <div class="eyebrow">Open in workbench</div>
  <div class="case-id">{html.escape(src_id)}</div>
  <div class="subject">{html.escape(str(draft_subj))}</div>
</div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
<div class="pd-case-banner empty">
  <div class="eyebrow">No case open</div>
  <div class="subject">Select a case from the inbox</div>
</div>
            """,
            unsafe_allow_html=True,
        )

    section_title = "Closed case" if case_closed else "Active request"
    st.markdown(
        f'<div class="pd-section"><div class="pd-section-title">{section_title}</div></div>',
        unsafe_allow_html=True,
    )
    # Only lock the form for true closed / lead / audit-replay of a closed case
    form_locked = role == "lead" or case_closed
    st.text_input("Subject", key="workspace_subject", disabled=form_locked)
    st.text_area(
        "Message body",
        key="workspace_body",
        height=180,
        disabled=form_locked,
    )

    if role == "agent" and not form_locked:
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
                st.session_state._pending_workspace = {
                    "subject": subj or uploaded.name,
                    "body": "\n".join(body_lines).strip() or raw,
                    "source_id": f"upload:{uploaded.name}",
                    "selected_inbox_id": None,
                    "last_result": None,
                }
                st.rerun()

        with st.expander(
            "Advanced — force playbook",
            expanded=str(st.session_state.get("force_branch") or "(auto)") != "(auto)",
        ):
            force_options = ["(auto)"] + [key for key, *_ in PLAYBOOKS]
            if st.session_state.get("force_branch") not in force_options:
                st.session_state.force_branch = "(auto)"
            st.selectbox(
                "Override classification",
                force_options,
                format_func=lambda k: (
                    "(auto — classify naturally)"
                    if k == "(auto)"
                    else f"{BRANCH_LABELS.get(k, k)}"
                ),
                key="force_branch",
                help="Pick a playbook, then click Run playbook. The forced branch is applied on that run.",
            )
            st.caption(
                "Select a branch here, then **Run playbook**. "
                "Useful for demos when the sample would otherwise classify differently."
            )

        force_pick = str(st.session_state.get("force_branch") or "(auto)")
        force_type = None if force_pick == "(auto)" else force_pick
        if force_type:
            st.info(
                f"Force playbook armed: **{BRANCH_LABELS.get(force_type, force_type)}** "
                f"(`{force_type}`). Click **Run playbook** to apply."
            )

        run_busy = bool(st.session_state.get("_run_busy"))
        run = st.button(
            "Run playbook",
            type="primary",
            width="stretch",
            disabled=run_busy,
            key="run_playbook",
        )
        if (run or bool(st.session_state.pop("auto_run", False))) and not run_busy:
            subject = (st.session_state.workspace_subject or "").strip()
            body = (st.session_state.workspace_body or "").strip()
            if not body:
                st.warning("Message body is required.")
            else:
                if not subject:
                    st.info("No subject entered — using “(no subject)”.")
                    subject = "(no subject)"
                # Re-read at click time — never trust a stale local from a prior path
                force_pick = str(st.session_state.get("force_branch") or "(auto)")
                force_type = None if force_pick == "(auto)" else force_pick
                st.session_state._run_busy = True
                try:
                    with st.spinner(
                        "Running playbook…"
                        + (f" (forced: {force_type})" if force_type else "")
                    ):
                        st.session_state.last_result = process_request(
                            subject,
                            body,
                            force_type=force_type,
                            assigned_to=user.get("username"),
                            actor=user.get("name"),
                        )
                    # Remount §5 draft widgets with the new email body
                    clear_draft_keys()
                    new_id = str(
                        (st.session_state.last_result or {}).get("case_id") or ""
                    )
                    st.session_state.workspace_source_id = new_id
                    st.session_state.selected_inbox_id = new_id
                    # Don't let inbox autofocus reload an older case over this run
                    st.session_state._suppress_inbox_autofocus = True
                    st.session_state._pending_inbox_filter = "Mine"
                    if force_type:
                        st.session_state._force_run_flash = force_type
                finally:
                    st.session_state._run_busy = False
                st.rerun()
    elif role == "agent" and form_locked:
        st.info(
            "This case is **Closed**. Reopen it from **Case Log → Replay on Process** "
            "to put it back on hold and release again."
        )

    result = st.session_state.get("last_result")
    force_flash = st.session_state.pop("_force_run_flash", None)
    if force_flash and result:
        st.success(
            f"Forced playbook applied: **{BRANCH_LABELS.get(str(force_flash), force_flash)}** "
            f"→ case `{result.get('case_id')}`."
        )
    if result:
        st.markdown("---")
        render_result_spine(result)
    elif role == "lead":
        st.markdown(
            """
<div class="pd-empty">
  <div class="pd-empty-title">Select an escalated case</div>
  <div class="pd-empty-hint">Open a case from the left queue to review and decide.</div>
</div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
<div class="pd-empty">
  <div class="pd-empty-title">Nothing selected</div>
  <div class="pd-empty-hint">Open a case from the inbox, or compose and run a playbook.</div>
</div>
            """,
            unsafe_allow_html=True,
        )
