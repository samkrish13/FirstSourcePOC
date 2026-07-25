"""Shared PulseDesk UI shell — ops workbench chrome.

Visual language: Zendesk / Freshdesk / ServiceNow Agent Workspace.
Metaphor: pick ticket → run playbook → everything is logged.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import streamlit as st

import db
from workflows.llm import (
    BRANCH_LABELS,
    CONFIDENCE_REVIEW_THRESHOLD,
    llm_available,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLES_PATH = ROOT / "data" / "sample_requests.json"

BRAND = "#2B6CB0"
INK = "#1F2933"
BG = "#F3F4F6"
SURFACE = "#FFFFFF"
LINE = "#D8DCE3"
MUTED = "#5B6570"
SOFT = "#EBF0F5"
SIDEBAR = "#1E2933"
ALERT_BG = "#FEF3C7"
ALERT_BORDER = "#D97706"
ALERT_INK = "#92400E"

PLAYBOOKS: list[tuple[str, str, str, str]] = [
    ("billing_dispute", "Billing Dispute", "Billing", "Hold → ticket → 48h follow-up"),
    ("service_outage", "Service Outage", "Network", "Bulletin match / Ops → SLA"),
    ("complaint_escalation", "Escalation", "Retention", "P1 → lead notify → callback"),
    ("sim_port", "SIM / Port", "Port/SIM", "Identity → ticket → 24h status"),
    ("plan_change", "Plan Change", "Care", "Eligibility → quote → confirm"),
    ("general_enquiry", "General Enquiry", "General", "FAQ → track → close/route"),
]

PLAYBOOK_BY_KEY: dict[str, tuple[str, str, str, str]] = {p[0]: p for p in PLAYBOOKS}


def load_samples() -> dict[str, Any]:
    return json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))


def all_inbox_items(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = data or load_samples()
    return [
        *( {**g, "lane": "golden"} for g in data.get("golden") or [] ),
        *( {**e, "lane": "edge"} for e in data.get("edge_cases") or [] ),
    ]


ROLE_PROFILES = {
    "agent": {"name": "P. Sharma", "title": "Agent", "initials": "PS"},
    "lead": {"name": "R. Mehta", "title": "Tech Lead", "initials": "RM"},
}

# Login stub — each person is a real account (not a costume switcher)
USERS: dict[str, dict[str, str]] = {
    "p.sharma": {
        "username": "p.sharma",
        "name": "P. Sharma",
        "role": "agent",
        "initials": "PS",
        "password": "agent",
    },
    "r.mehta": {
        "username": "r.mehta",
        "name": "R. Mehta",
        "role": "lead",
        "initials": "RM",
        "password": "lead",
    },
}

ESCALATE_REASONS = [
    "Low confidence / ambiguous intent",
    "Policy exception required",
    "Customer threatened regulatory action",
    "Refund / goodwill above agent limit",
    "Other — see note",
]
RETURN_REASONS = [
    "Need more customer information",
    "Draft needs rewrite",
    "Wrong playbook — reclassify",
    "Within agent authority after guidance",
    "Other — see note",
]


def ensure_state() -> None:
    defaults = {
        "selected_inbox_id": None,
        "workspace_subject": "",
        "workspace_body": "",
        "workspace_source_id": None,
        "last_result": None,
        "case_log_focus": None,
        "compare_slot_count": 2,
        "compare_results": [],
        "compare_result_labels": [],
        "force_branch": "(auto)",
        "current_user": None,
        "lead_queue_focus": None,
        "inbox_filter": "Mine",
        "demo_seeded": False,
        "tour_done": {},
        "show_tour": False,
        "tour_step": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def current_user() -> dict[str, str] | None:
    user = st.session_state.get("current_user")
    return user if isinstance(user, dict) else None


def active_role() -> str:
    user = current_user()
    if user and user.get("role") in ROLE_PROFILES:
        return str(user["role"])
    return "agent"


def require_login() -> dict[str, str] | None:
    """Gate UI behind stub login. Returns user or None while login form is shown."""
    ensure_state()
    user = current_user()
    if user:
        return user

    st.markdown(
        f"""
<div class="pd-page-head">
  <h1>PulseDesk sign-in</h1>
  <div class="desc">Use your desk account. Lead actions only appear for Tech Lead accounts.</div>
</div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("login_form"):
        username = st.selectbox(
            "Account",
            list(USERS.keys()),
            format_func=lambda u: f"{USERS[u]['name']} · {USERS[u]['role'].title()}",
        )
        password = st.text_input("Password", type="password")
        st.caption("Demo passwords: **agent** (P. Sharma) · **lead** (R. Mehta)")
        submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
    if submitted:
        account = USERS.get(username) or {}
        if account.get("password") == password:
            st.session_state.current_user = {
                "username": account["username"],
                "name": account["name"],
                "role": account["role"],
                "initials": account["initials"],
            }
            done = st.session_state.setdefault("tour_done", {})
            if not done.get(account["username"]):
                st.session_state.show_tour = True
                st.session_state.tour_step = 0
            st.rerun()
        st.error("Incorrect password.")
    return None


def logout() -> None:
    st.session_state.current_user = None
    st.session_state.last_result = None
    st.session_state.show_tour = False
    st.rerun()


def _tour_steps_for(user: dict[str, str]) -> list[tuple[str, str]]:
    name = user.get("name") or "you"
    if user.get("role") == "lead":
        return [
            (
                "Welcome — you're signed in as Tech Lead",
                f"You are **{name}**. You only see **escalated** work. "
                "Agent release/edit controls stay hidden.",
            ),
            (
                "1 · Escalated queue",
                "Left rail lists cases agents escalated. Open one to review classification, "
                "timeline, and draft.",
            ),
            (
                "2 · Lead actions",
                "**Acknowledge** ownership, **Approve release** (simulated until email), or "
                "**Return to agent** with a **required reason** and a **note the agent will see**.",
            ),
            (
                "3 · Status that sticks",
                "Lifecycle is **Open → On hold → Escalated → Released / Returned**, "
                "with who/when on the case.",
            ),
        ]
    return [
        (
            "Welcome — you're signed in as an agent",
            f"You are **{name}**. Only your account sees agent actions "
            "(Edit / Release / Escalate). Tech Leads sign in separately — "
            "no costume role switcher.",
        ),
        (
            "1 · Work inbox (left)",
            "Cases arrive in **Mine / Unassigned / All**. Use **Claim** to take ownership. "
            "Each row shows status, received time, and an **SLA countdown** that updates as you work.",
        ),
        (
            "2 · Compose or load a case",
            "**Compose** for a blank ticket, or open a case from the inbox. "
            "Optional: expand **Load demo sample** for practice data.",
        ),
        (
            "3 · Run playbook",
            "Click **Run playbook**. PulseDesk classifies the request, picks a branch, builds a draft, "
            "and logs everything. Low confidence → **On hold / Needs Review**.",
        ),
        (
            "4 · Read the spine",
            "Scroll the result: **Why this branch**, **What I'm unsure about**, timeline, draft, "
            "then **Queue · ticket · follow-up** in plain ops language.",
        ),
        (
            "5 · Release or escalate",
            "On hold cases: **Edit → Save → Release draft**, or **Escalate to lead** with a "
            "**reason code**. Outbound stays labeled simulated until email is wired.",
        ),
        (
            "6 · Coach compare (optional)",
            "**Coach: compare playbooks** opens a popup to see how e.g. Billing vs Outage differ — "
            "training only, nothing written to Case Log.",
        ),
    ]


@st.dialog("PulseDesk guided tour", width="large")
def _guided_tour_dialog() -> None:
    user = current_user() or {}
    steps = _tour_steps_for(user)
    n = len(steps)
    step = int(st.session_state.get("tour_step") or 0)
    step = max(0, min(step, n - 1))
    title, body = steps[step]

    st.progress((step + 1) / n, text=f"Step {step + 1} of {n}")
    st.markdown(f"### {title}")
    st.markdown(body)
    st.caption("Replay anytime from **Take tour** in the top bar.")

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("Back", width="stretch", disabled=step <= 0, key="tour_back"):
            st.session_state.tour_step = step - 1
            st.rerun()
    with b2:
        if st.button("Skip tour", width="stretch", key="tour_skip"):
            _finish_tour(user.get("username") or "")
            st.rerun()
    with b3:
        if step >= n - 1:
            if st.button("Finish", type="primary", width="stretch", key="tour_finish"):
                _finish_tour(user.get("username") or "")
                st.rerun()
        elif st.button("Next", type="primary", width="stretch", key="tour_next"):
            st.session_state.tour_step = step + 1
            st.rerun()


def _finish_tour(username: str) -> None:
    st.session_state.show_tour = False
    st.session_state.tour_step = 0
    done = st.session_state.setdefault("tour_done", {})
    if username:
        done[username] = True


def start_guided_tour() -> None:
    """Open / restart the first-time user tour."""
    st.session_state.show_tour = True
    st.session_state.tour_step = 0


def render_guided_tour_if_needed() -> None:
    if st.session_state.get("show_tour"):
        _guided_tour_dialog()


def _clear_draft_keys() -> None:
    for k in list(st.session_state.keys()):
        sk = str(k)
        if sk.startswith(("draft_edit_mode_", "draft_baseline_")) or (
            sk.startswith("draft_") and sk.endswith(("_view", "_edit"))
        ):
            st.session_state.pop(k, None)


def compose_new_request() -> None:
    """Blank Process form for freeform classification demos."""
    st.session_state.workspace_subject = ""
    st.session_state.workspace_body = ""
    st.session_state.workspace_source_id = "manual:compose"
    st.session_state.last_result = None
    st.session_state.pop("replay_banner", None)
    _clear_draft_keys()


def open_in_workspace(item: dict[str, Any]) -> None:
    st.session_state.selected_inbox_id = item["id"]
    st.session_state.workspace_source_id = item["id"]
    st.session_state.workspace_subject = item.get("subject") or ""
    st.session_state.workspace_body = item.get("body") or ""
    st.session_state.last_result = None
    st.session_state.pop("replay_banner", None)
    _clear_draft_keys()


def inject_css() -> None:
    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {{
  font-family: "IBM Plex Sans", system-ui, sans-serif;
  color: {INK};
  font-size: 15px;
}}
code, pre, .pd-mono {{
  font-family: "IBM Plex Mono", ui-monospace, monospace;
}}

.stApp {{ background: {BG}; }}
section.main > div {{ max-width: 100% !important; }}
div[data-testid="stAppViewContainer"] > .main {{ overflow-x: hidden; }}
#MainMenu, footer {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ display: none !important; }}
section[data-testid="stSidebar"],
div[data-testid="stSidebarCollapsedControl"] {{ display: none !important; }}

.block-container {{
  max-width: 100% !important;
  width: 100% !important;
  padding-top: 0.35rem !important;
  padding-bottom: 2rem !important;
  padding-left: 1.25rem !important;
  padding-right: 1.25rem !important;
}}

.pd-primary {{
  width: 100vw;
  max-width: 100vw;
  position: relative;
  left: 50%;
  margin-left: -50vw;
  margin-right: -50vw;
  box-sizing: border-box;
  padding-left: max(1.25rem, calc((100vw - 100%) / 2 + 1.25rem));
  padding-right: max(1.25rem, calc((100vw - 100%) / 2 + 1.25rem));
}}

.pd-nav-row {{
  margin: 0 0 0.45rem 0;
  padding-bottom: 0.35rem;
  border-bottom: 1px solid {LINE};
}}

.pd-role-avatar {{
  width: 22px; height: 22px;
  border-radius: 50%;
  background: {BRAND};
  color: #fff;
  font-size: 0.62rem;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}}

/* Profile popover — circular avatar, aligned with nav */
div[data-testid="stPopover"] {{
  display: flex !important;
  justify-content: flex-end !important;
  align-items: center !important;
  height: 100%;
  min-height: 2.5rem;
}}
div[data-testid="stPopover"] > div {{
  display: flex !important;
  align-items: center !important;
}}
div[data-testid="stPopover"] button {{
  border-radius: 50% !important;
  width: 2.25rem !important;
  height: 2.25rem !important;
  min-width: 2.25rem !important;
  min-height: 2.25rem !important;
  max-width: 2.25rem !important;
  padding: 0 !important;
  margin: 0 !important;
  background: {BRAND} !important;
  color: #fff !important;
  border: 2px solid #fff !important;
  box-shadow: 0 0 0 1px {LINE} !important;
  font-size: 0.7rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.02em;
  line-height: 1 !important;
  overflow: visible !important;
}}
div[data-testid="stPopover"] button:hover {{
  background: #1E4E8C !important;
  color: #fff !important;
  border-color: #fff !important;
}}
div[data-testid="stPopover"] button p,
div[data-testid="stPopover"] button span {{
  color: #fff !important;
  font-weight: 700 !important;
  line-height: 1 !important;
}}

.pd-profile-menu .name {{
  font-weight: 700;
  font-size: 0.95rem;
  color: {INK};
  margin: 0;
}}
.pd-profile-menu .role {{
  font-size: 0.8rem;
  color: {MUTED};
  margin: 0.15rem 0 0.65rem 0;
}}

.pd-brand-lockup {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.15rem 1rem 0.15rem 0;
  padding-right: 0.9rem;
  border-right: 1px solid {LINE};
  white-space: nowrap;
  min-height: 2.5rem;
}}
.pd-mark {{
  width: 28px; height: 28px;
  background: {BRAND};
  color: #fff;
  font-size: 0.68rem;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  flex-shrink: 0;
}}
.pd-product {{
  font-weight: 700;
  font-size: 1.05rem;
  letter-spacing: -0.01em;
  color: {INK};
  line-height: 1.2;
}}

a[data-testid="stPageLink-NavLink"] {{
  text-decoration: none !important;
  color: {INK} !important;
  font-weight: 550 !important;
  font-size: 0.9rem !important;
  padding: 0.55rem 0.5rem 0.6rem !important;
  border-bottom: 2px solid transparent !important;
  border-radius: 0 !important;
  background: transparent !important;
}}
a[data-testid="stPageLink-NavLink"]:hover {{
  color: {BRAND} !important;
}}
a[data-testid="stPageLink-NavLink"][aria-current="page"],
a[data-testid="stPageLink-NavLink"][aria-selected="true"] {{
  color: {BRAND} !important;
  font-weight: 700 !important;
  border-bottom-color: {BRAND} !important;
}}

.pd-page-head {{ margin: 0.1rem 0 0.85rem 0; }}
.pd-page-head h1 {{
  margin: 0;
  font-size: 1.2rem;
  font-weight: 650;
  letter-spacing: -0.01em;
}}
.pd-page-head .desc {{
  margin-top: 0.2rem;
  font-size: 0.88rem;
  color: {MUTED};
  max-width: 70ch;
  line-height: 1.45;
}}

.pd-section {{
  background: {SURFACE};
  border: 1px solid {LINE};
  border-radius: 6px;
  padding: 0.85rem 1rem;
  margin-bottom: 0.75rem;
}}
.pd-section-title {{
  font-size: 0.7rem;
  font-weight: 650;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: {MUTED};
  margin-bottom: 0.55rem;
}}
.pd-section h3 {{
  margin: 0 0 0.4rem 0;
  font-size: 1rem;
  font-weight: 650;
}}

.pd-rail-title {{
  font-size: 0.7rem;
  font-weight: 650;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: {MUTED};
  margin-bottom: 0.45rem;
}}

.pd-inbox-item {{
  border: 1px solid {LINE};
  border-radius: 6px;
  background: {SURFACE};
  padding: 0.55rem 0.65rem;
  margin-bottom: 0.4rem;
  font-size: 0.84rem;
}}
.pd-inbox-item.active {{
  border-color: {BRAND};
  box-shadow: inset 3px 0 0 {BRAND};
}}
.pd-inbox-id {{
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.72rem;
  color: {MUTED};
}}
.pd-inbox-subject {{
  font-weight: 600;
  color: {INK};
  margin-top: 0.15rem;
  line-height: 1.3;
}}
.pd-inbox-meta {{
  margin-top: 0.2rem;
  font-size: 0.75rem;
  color: {MUTED};
}}

/* Mail-style work inbox (email-client list) */
.pd-mail-panel {{
  background: {SURFACE};
  border: 1px solid {LINE};
  border-radius: 14px;
  padding: 0.75rem 0.7rem 0.55rem;
  box-shadow: 0 1px 2px rgba(31, 41, 51, 0.04);
}}
.pd-mail-head {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.55rem;
  padding: 0 0.15rem;
}}
.pd-mail-head .title {{
  font-size: 0.95rem;
  font-weight: 650;
  color: {INK};
  letter-spacing: -0.01em;
}}
.pd-mail-head .count {{
  font-size: 0.72rem;
  font-weight: 600;
  color: {MUTED};
  background: #EEF2F6;
  border-radius: 999px;
  padding: 0.12rem 0.5rem;
}}
.pd-mail-row {{
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  padding: 0.65rem 0.6rem;
  margin: 0.28rem 0;
  border: 1px solid transparent;
  border-radius: 12px;
  background: #FAFBFC;
  transition: border-color 0.12s ease, background 0.12s ease;
}}
.pd-mail-row.on {{
  background: #fff;
  border-color: {BRAND};
  box-shadow: 0 0 0 1px rgba(43, 108, 176, 0.12);
}}
.pd-mail-dot {{
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-top: 0.55rem;
  flex-shrink: 0;
  background: transparent;
}}
.pd-mail-dot.unread {{ background: {BRAND}; }}
.pd-mail-avatar {{
  width: 32px;
  height: 32px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.68rem;
  font-weight: 700;
  color: #fff;
  margin-top: 0.1rem;
}}
.pd-mail-body {{
  flex: 1;
  min-width: 0;
}}
.pd-mail-top {{
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem 0.4rem;
  margin-bottom: 0.2rem;
}}
.pd-mail-from {{
  font-size: 0.82rem;
  font-weight: 650;
  color: {INK};
}}
.pd-mail-tag {{
  display: inline-block;
  font-size: 0.62rem;
  font-weight: 650;
  letter-spacing: 0.02em;
  padding: 0.12rem 0.42rem;
  border-radius: 999px;
  line-height: 1.2;
  white-space: nowrap;
}}
.pd-mail-tag.st-open {{ background: #E8F1F8; color: {BRAND}; }}
.pd-mail-tag.st-on_hold {{ background: #FEF3C7; color: #92400E; }}
.pd-mail-tag.st-escalated {{ background: #FEE2E2; color: #991B1B; }}
.pd-mail-tag.st-released {{ background: #DCFCE7; color: #166534; }}
.pd-mail-tag.st-returned {{ background: #EEF2F6; color: #475569; }}
.pd-mail-tag.branch {{ background: #F1F5F9; color: #334155; }}
.pd-mail-subline {{
  font-size: 0.78rem;
  line-height: 1.35;
  color: {MUTED};
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}}
.pd-mail-subline strong {{
  color: {INK};
  font-weight: 600;
}}
.pd-mail-aside {{
  flex-shrink: 0;
  text-align: right;
  min-width: 4.2rem;
  padding-top: 0.15rem;
}}
.pd-mail-time {{
  font-size: 0.68rem;
  color: {MUTED};
  white-space: nowrap;
}}
.pd-mail-sla {{
  margin-top: 0.25rem;
  font-size: 0.62rem;
  font-weight: 650;
  color: {BRAND};
  background: #E8F1F8;
  border-radius: 999px;
  padding: 0.14rem 0.4rem;
  display: inline-block;
  max-width: 5.5rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.pd-mail-sla.overdue {{
  color: #991B1B;
  background: #FEE2E2;
}}
.pd-mail-empty {{
  padding: 1.1rem 0.6rem;
  text-align: center;
  color: {MUTED};
  font-size: 0.82rem;
}}
/* Compact Open control beside each mail row */
div[data-testid="stVerticalBlock"]:has(.pd-mail-row) div[data-testid="stButton"] > button {{
  margin-top: 0.85rem !important;
  min-height: 2.4rem !important;
  height: 2.4rem !important;
  padding: 0 0.35rem !important;
  font-size: 0.72rem !important;
  font-weight: 650 !important;
  border-radius: 10px !important;
}}

.pd-playbook-rail {{
  margin-top: 0.85rem;
  border: 1px solid {LINE};
  border-radius: 6px;
  background: {SURFACE};
  padding: 0.7rem 0.75rem;
}}
.pd-playbook-rail .hd {{
  font-size: 0.68rem;
  font-weight: 650;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: {MUTED};
  margin-bottom: 0.45rem;
}}
.pd-playbook-rail .name {{
  font-size: 0.95rem;
  font-weight: 700;
  color: {BRAND};
  margin-bottom: 0.2rem;
}}
.pd-playbook-rail .meta {{
  font-size: 0.78rem;
  color: {MUTED};
  margin-bottom: 0.55rem;
  line-height: 1.35;
}}
.pd-playbook-rail .step {{
  font-size: 0.78rem;
  color: {INK};
  padding: 0.28rem 0;
  border-top: 1px solid {LINE};
  line-height: 1.35;
}}
.pd-playbook-rail .step .a {{
  font-size: 0.66rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: {BRAND};
}}
.pd-playbook-rail .others {{
  margin-top: 0.65rem;
  padding-top: 0.55rem;
  border-top: 1px solid {LINE};
}}
.pd-playbook-rail .others .row {{
  font-size: 0.74rem;
  color: {MUTED};
  padding: 0.18rem 0;
}}
.pd-playbook-rail .others .row.on {{
  color: {INK};
  font-weight: 600;
}}

.pd-chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin: 0.35rem 0 0.55rem 0;
}}
.pd-chip {{
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  border: 1px solid {LINE};
  background: {SOFT};
  color: {INK};
  padding: 0.18rem 0.45rem;
  border-radius: 4px;
}}
.pd-chip.type {{ border-color: {BRAND}; color: {BRAND}; background: #E8F1F8; }}
.pd-chip.review {{
  border-color: {ALERT_BORDER};
  background: {ALERT_BG};
  color: {ALERT_INK};
}}

.pd-alert {{
  border: 1px solid {ALERT_BORDER};
  border-left: 4px solid {ALERT_BORDER};
  background: {ALERT_BG};
  color: {ALERT_INK};
  padding: 0.85rem 1rem;
  font-size: 0.92rem;
  line-height: 1.45;
  border-radius: 6px;
  margin-bottom: 0.85rem;
}}
.pd-alert strong {{ color: {ALERT_INK}; }}

.pd-type {{
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin: 0 0 0.15rem 0;
}}
.pd-body {{
  font-size: 0.9rem;
  line-height: 1.5;
  color: {INK};
}}

.pd-dl {{
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: 0.25rem 0.55rem;
  font-size: 0.86rem;
  margin-top: 0.35rem;
}}
.pd-dl .k {{ color: {MUTED}; }}
.pd-dl .v {{ color: {INK}; font-weight: 500; }}

.pd-branch {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.4rem;
}}
.pd-node {{
  border: 1px solid {LINE};
  border-radius: 6px;
  padding: 0.5rem 0.55rem;
  background: {BG};
  font-size: 0.8rem;
  color: {MUTED};
}}
.pd-node .nm {{ font-weight: 600; color: {INK}; font-size: 0.84rem; }}
.pd-node .q {{ font-size: 0.72rem; margin-top: 0.1rem; }}
.pd-node.on {{
  border-color: {BRAND};
  background: #E8F1F8;
  color: {INK};
  box-shadow: inset 0 0 0 1px {BRAND};
}}
.pd-node.on .nm {{ color: {BRAND}; font-weight: 700; }}

.pd-step {{
  display: grid;
  grid-template-columns: 1.7rem 1fr;
  gap: 0.5rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid {LINE};
}}
.pd-step:last-child {{ border-bottom: none; }}
.pd-step .n {{
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.72rem;
  color: {MUTED};
  padding-top: 0.12rem;
}}
.pd-step .a {{
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: {BRAND};
}}
.pd-step .d {{
  font-size: 0.88rem;
  color: {INK};
  line-height: 1.4;
  margin-top: 0.08rem;
}}

.pd-callout-row {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.65rem;
}}
.pd-callout {{
  border: 1px solid {LINE};
  border-radius: 6px;
  padding: 0.7rem 0.8rem;
  background: {BG};
}}
.pd-callout .lbl {{
  font-size: 0.68rem;
  font-weight: 650;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: {MUTED};
}}
.pd-callout .val {{
  margin-top: 0.25rem;
  font-size: 0.95rem;
  font-weight: 650;
  color: {INK};
}}
.pd-callout .sub {{
  margin-top: 0.2rem;
  font-size: 0.82rem;
  color: {MUTED};
  line-height: 1.4;
}}

.pd-checklist {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem 1rem;
  font-size: 0.84rem;
  color: {INK};
  margin-top: 0.15rem;
}}
.pd-checklist .ok {{ color: #1F6B3A; font-weight: 650; }}
.pd-checklist .miss {{ color: {MUTED}; }}

.pd-gate {{
  border: 1px solid {ALERT_BORDER};
  border-left: 4px solid {ALERT_BORDER};
  background: {ALERT_BG};
  color: {ALERT_INK};
  padding: 0.85rem 1rem;
  border-radius: 6px;
  margin-bottom: 0.85rem;
}}
.pd-gate .note {{
  font-size: 0.82rem;
  margin-top: 0.35rem;
  opacity: 0.95;
}}
.pd-decision {{
  border: 1px solid {LINE};
  background: #E8F1F8;
  color: {INK};
  padding: 0.65rem 0.85rem;
  border-radius: 6px;
  margin-bottom: 0.75rem;
  font-size: 0.88rem;
}}

.pd-compare-col {{
  border: 1px solid {LINE};
  border-radius: 6px;
  background: {SURFACE};
  padding: 0.75rem 0.85rem;
}}
.pd-compare-col .hd {{
  font-size: 0.7rem;
  font-weight: 650;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: {MUTED};
  margin-bottom: 0.35rem;
}}
.pd-compare-col .title {{
  font-weight: 700;
  font-size: 0.95rem;
  color: {BRAND};
  margin-bottom: 0.45rem;
}}
.pd-compare-step {{
  font-size: 0.8rem;
  padding: 0.28rem 0;
  border-bottom: 1px solid {LINE};
  color: {INK};
}}
.pd-compare-step .a {{
  font-weight: 700;
  font-size: 0.68rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: {BRAND};
}}

.pd-quiet {{
  font-size: 0.78rem;
  color: {MUTED};
  margin-top: 0.35rem;
}}

.pd-outputs {{
  display: grid;
  gap: 0.15rem;
}}
.pd-out-row {{
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 0.5rem;
  padding: 0.4rem 0;
  border-bottom: 1px solid {LINE};
  font-size: 0.86rem;
}}
.pd-out-row:last-child {{ border-bottom: none; }}
.pd-out-row .k {{
  color: {MUTED};
  font-size: 0.7rem;
  font-weight: 650;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding-top: 0.12rem;
}}
.pd-out-row .v {{ color: {INK}; line-height: 1.4; word-break: break-word; }}
.pd-out-row .v.flag {{ font-weight: 650; color: {BRAND}; }}
.pd-out-row .v.warn {{ font-weight: 650; color: {ALERT_INK}; }}
.pd-out-row .v.ok {{ font-weight: 650; color: #1F6B3A; }}

/* Top toaster stack — notifications / alerts / flags */
.pd-toast-stack {{
  position: sticky;
  top: 0.35rem;
  z-index: 40;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  margin: 0 0 0.9rem 0;
}}
.pd-toast {{
  display: grid;
  grid-template-columns: 4.6rem 1fr;
  gap: 0.65rem;
  align-items: start;
  background: {SURFACE};
  border: 1px solid {LINE};
  border-radius: 8px;
  padding: 0.65rem 0.8rem;
  box-shadow: 0 6px 18px rgba(31, 41, 51, 0.08);
  animation: pdToastIn 0.32s ease-out;
}}
.pd-toast .kind {{
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 0.2rem 0.35rem;
  border-radius: 4px;
  text-align: center;
  line-height: 1.2;
}}
.pd-toast .body {{
  font-size: 0.86rem;
  line-height: 1.4;
  color: {INK};
}}
.pd-toast .body strong {{
  display: block;
  font-size: 0.8rem;
  margin-bottom: 0.12rem;
}}
.pd-toast.notify {{ border-left: 4px solid {BRAND}; }}
.pd-toast.notify .kind {{ background: #E8F1F8; color: {BRAND}; }}
.pd-toast.alert {{ border-left: 4px solid {ALERT_BORDER}; }}
.pd-toast.alert .kind {{ background: {ALERT_BG}; color: {ALERT_INK}; }}
.pd-toast.flag {{ border-left: 4px solid #0F766E; }}
.pd-toast.flag .kind {{ background: #CCFBF1; color: #0F766E; }}
.pd-toast.ok {{ border-left: 4px solid #1F6B3A; }}
.pd-toast.ok .kind {{ background: #E8F5EC; color: #1F6B3A; }}
@keyframes pdToastIn {{
  from {{ opacity: 0; transform: translateY(-8px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}

div.stButton > button[kind="primary"] {{
  background: {BRAND};
  border-color: {BRAND};
  border-radius: 6px;
}}
div.stButton > button {{
  border-radius: 6px;
  border-color: {LINE};
  font-weight: 550;
}}

/* Branch compare dialog — steel-blue popup (PulseDesk palette) */
div[data-testid="stDialog"] > div:first-child {{
  border: 1px solid {BRAND} !important;
  border-radius: 12px !important;
  box-shadow:
    0 0 0 1px rgba(43, 108, 176, 0.2),
    0 0 28px rgba(43, 108, 176, 0.22),
    0 18px 48px rgba(31, 41, 51, 0.18) !important;
  background: {SURFACE} !important;
  max-width: 920px !important;
}}
div[data-testid="stDialog"] [data-testid="stMarkdownContainer"] h1,
div[data-testid="stDialog"] [data-testid="stMarkdownContainer"] h2 {{
  color: {INK} !important;
}}

@media (max-width: 900px) {{
  .pd-branch {{ grid-template-columns: 1fr 1fr; }}
  .pd-callout-row {{ grid-template-columns: 1fr; }}
  .pd-out-row {{ grid-template-columns: 1fr; }}
}}
</style>
        """,
        unsafe_allow_html=True,
    )


def page_setup(_title: str = "PulseDesk", icon: str = "▣") -> None:
    del icon
    inject_css()
    ensure_state()
    db.init_db()


NAV_LINKS: list[tuple[str, str]] = [
    ("pages/0_Process.py", "Process"),
    ("pages/1_Case_Log.py", "Case Log"),
    ("pages/2_Playbooks.py", "Playbooks"),
]


def chrome(active: str = "process") -> bool:
    """Top nav for signed-in users. Returns False if login form is showing."""
    del active
    user = current_user()
    if not user:
        require_login()
        return False

    role_title = ROLE_PROFILES.get(user.get("role") or "", {}).get("title") or (
        user.get("role") or "User"
    ).title()

    brand, n1, n2, n3, tour_col, profile_col = st.columns(
        [1.4, 0.75, 0.9, 0.95, 0.8, 0.55]
    )
    with brand:
        st.markdown(
            """
<div class="pd-brand-lockup">
  <span class="pd-mark">PD</span>
  <span class="pd-product">PulseDesk</span>
</div>
            """,
            unsafe_allow_html=True,
        )
    for col, (path_name, label) in zip((n1, n2, n3), NAV_LINKS):
        with col:
            st.page_link(path_name, label=label)
    with tour_col:
        if st.button("Take tour", width="stretch", key="take_tour"):
            start_guided_tour()
            st.rerun()
    with profile_col:
        with st.popover(
            user.get("initials") or "?",
            help="Account — name, role, sign out",
        ):
            st.markdown(
                f"""
<div class="pd-profile-menu">
  <p class="name">{_esc_html(user.get("name") or "")}</p>
  <p class="role">{_esc_html(role_title)}</p>
</div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Sign out", type="primary", width="stretch", key="sign_out"):
                logout()
    st.markdown('<div class="pd-nav-row"></div>', unsafe_allow_html=True)
    render_guided_tour_if_needed()
    return True


def page_header(title: str, desc: str = "") -> None:
    desc_html = f'<div class="desc">{desc}</div>' if desc else ""
    st.markdown(
        f'<div class="pd-page-head"><h1>{title}</h1>{desc_html}</div>',
        unsafe_allow_html=True,
    )


def render_playbook_rail(
    *,
    sample_branch: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    """Left-rail playbook card — fills empty space under the sample list."""
    active_key = sample_branch or ""
    ran = False
    live_steps: list[dict[str, Any]] = []
    if result:
        clf = result.get("classification") or {}
        rem = result.get("remediation") or {}
        active_key = str(clf.get("request_type") or rem.get("branch") or active_key)
        live_steps = list(rem.get("steps") or [])
        ran = True

    pb = PLAYBOOK_BY_KEY.get(active_key)
    if not pb:
        # Fall back to first playbook hint from sample
        for key, *_rest in PLAYBOOKS:
            if key == sample_branch:
                pb = PLAYBOOK_BY_KEY[key]
                active_key = key
                break
    if not pb:
        st.caption("Select a sample to preview its playbook.")
        return

    _key, name, queue, summary = pb
    status = "Active after Run" if ran else "Expected for this sample"
    steps_html: list[str] = []
    if ran and live_steps:
        for i, step in enumerate(live_steps[:8], start=1):
            action = step.get("action_type") or "action"
            detail = str(step.get("detail") or "")[:90]
            steps_html.append(
                f'<div class="step"><span class="a">{i:02d} · {_esc_html(action)}</span>'
                f"<br/>{_esc_html(detail)}</div>"
            )
    else:
        for i, part in enumerate([p.strip() for p in summary.split("→")], start=1):
            steps_html.append(
                f'<div class="step"><span class="a">{i:02d}</span><br/>{_esc_html(part)}</div>'
            )

    others = []
    for key, oname, oqueue, _osum in PLAYBOOKS:
        cls = "on" if key == active_key else ""
        others.append(
            f'<div class="row {cls}">{_esc_html(oname)} · {_esc_html(oqueue)}</div>'
        )

    st.markdown(
        f"""
<div class="pd-playbook-rail">
  <div class="hd">Playbook · {status}</div>
  <div class="name">{_esc_html(name)}</div>
  <div class="meta">Queue <strong>{_esc_html(queue)}</strong><br/>Strategy: {_esc_html(summary)}</div>
  {"".join(steps_html)}
  <div class="others">
    <div class="hd" style="margin-bottom:0.25rem;">All six paths</div>
    {"".join(others)}
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def branch_label(key: str) -> str:
    return BRANCH_LABELS.get(key, key)


def _follow_up_detail(steps: list[dict[str, Any]]) -> str:
    for key in ("schedule_follow_up", "set_sla_clock", "set_callback", "close_or_route"):
        for s in steps:
            if s.get("action_type") == key:
                return str(s.get("detail") or key)
    return "—"


def _route_detail(rem: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    for s in steps:
        if s.get("action_type") == "route_to_team":
            return str(s.get("detail") or rem.get("summary") or "—")
    return str(rem.get("summary") or "—")


def _outcome_flags(rem: dict[str, Any], steps: list[dict[str, Any]], case_id: str) -> dict[str, bool]:
    follow = _follow_up_detail(steps)
    has_route = bool(rem.get("queue")) or any(
        s.get("action_type") == "route_to_team" for s in steps
    )
    return {
        "response": bool((rem.get("email_draft") or "").strip()),
        "route": has_route,
        "follow_up": follow != "—",
        "log": bool(case_id),
    }


def _json_obj(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _payload_dict(step: dict[str, Any]) -> dict[str, Any]:
    return _json_obj(step.get("payload"))


def _decision_from_actions(case_id: str) -> tuple[str | None, str | None]:
    """Return (agent_decision, lead_decision) from latest matching audit actions."""
    agent_map = {
        "agent_approved_send": "approved_send",
        "agent_edited_send": "edited_send",
        "agent_escalated_to_lead": "escalated_lead",
    }
    lead_map = {
        "lead_acknowledged": "acknowledged",
        "lead_approved_release": "approved_release",
        "lead_returned_to_agent": "returned_to_agent",
        "lead_note": "note",
    }
    agent_decision = lead_decision = None
    for a in db.get_case_actions(case_id):
        t = a.get("action_type") or ""
        if t in agent_map:
            agent_decision = agent_map[t]
        if t in lead_map:
            lead_decision = lead_map[t]
    if lead_decision == "returned_to_agent":
        agent_decision = None
    return agent_decision, lead_decision


def rebuild_result_from_case(case_id: str) -> dict[str, Any] | None:
    """Hydrate a Process spine result from SQLite (Case Log replay)."""
    case = db.get_case(case_id)
    if not case:
        return None

    clf = _json_obj(case.get("classification_json"))
    entities = _json_obj(case.get("entities_json"))

    if not clf.get("request_type"):
        clf = {
            "request_type": case.get("request_type"),
            "confidence": case.get("confidence"),
            "urgency": case.get("urgency"),
            "sentiment": case.get("sentiment"),
            "entities": entities,
            "rationale": clf.get("rationale") or "Replayed from Case Log.",
            "mode": clf.get("mode") or "replay",
        }
    else:
        clf.setdefault("entities", entities)

    steps: list[dict[str, Any]] = []
    ticket_id = None
    queue = None
    for a in db.get_case_actions(case_id):
        payload = _json_obj(a.get("payload_json"))
        steps.append(
            {
                "action_type": a.get("action_type"),
                "detail": a.get("detail"),
                "payload": payload,
            }
        )
        ticket_id = ticket_id or payload.get("ticket_id")
        queue = queue or payload.get("queue") or payload.get("team")

    draft = next(
        (
            m.get("content") or ""
            for m in db.get_case_messages(case_id)
            if m.get("direction") == "outbound" and (m.get("content") or "").strip()
        ),
        "",
    )

    request_type = case.get("request_type") or clf.get("request_type") or ""
    rem = {
        "branch": request_type,
        "branch_label": branch_label(request_type),
        "steps": steps,
        "email_draft": draft,
        "ticket_id": ticket_id,
        "queue": queue,
        "summary": "",
    }
    needs_review = bool(case.get("needs_review"))
    from workflows.outputs import build_case_outputs

    outputs = build_case_outputs(
        clf,
        rem,
        needs_review=needs_review,
        case_id=case_id,
    )
    rem["outputs"] = outputs
    agent_decision, lead_decision = _decision_from_actions(case_id)
    return {
        "case_id": case_id,
        "classification": clf,
        "needs_review": needs_review,
        "remediation": rem,
        "outputs": outputs,
        "replay": True,
        "agent_decision": agent_decision,
        "lead_decision": lead_decision,
        "status": case.get("status") or db.STATUS_OPEN,
        "assigned_to": case.get("assigned_to"),
        "status_updated_at": case.get("status_updated_at"),
        "status_updated_by": case.get("status_updated_by"),
        "escalate_reason": case.get("escalate_reason"),
        "return_reason": case.get("return_reason"),
        "lead_note_to_agent": case.get("lead_note_to_agent"),
        "sla_due_at": case.get("sla_due_at"),
        "received_at": case.get("received_at") or case.get("created_at"),
    }


def save_agent_draft(result: dict[str, Any], draft: str) -> dict[str, Any]:
    """Persist edited draft without releasing the case (Save only)."""
    case_id = result.get("case_id") or ""
    if not case_id:
        return result

    rem = dict(result.get("remediation") or {})
    rem["email_draft"] = draft
    steps = list(rem.get("steps") or [])
    steps.append(
        {
            "action_type": "agent_saved_draft",
            "detail": "Agent saved edited draft — still held for review (not sent).",
            "payload": {"draft_chars": len(draft or ""), "saved": True},
        }
    )
    rem["steps"] = steps
    result["remediation"] = rem
    result["draft_saved"] = True
    result["draft_saved_text"] = draft

    order = db.next_action_order(case_id)
    db.log_action(
        case_id,
        order,
        "agent_saved_draft",
        "Agent saved edited draft — still held for review (not sent).",
        {"draft_chars": len(draft or ""), "saved": True},
    )
    return result


def apply_agent_decision(
    result: dict[str, Any],
    decision: str,
    draft: str,
    *,
    reason: str = "",
) -> dict[str, Any]:
    """Log Release / Escalate and update case status (who/when)."""
    case_id = result.get("case_id") or ""
    if not case_id:
        return result

    user = current_user() or {}
    actor = user.get("name") or user.get("username") or "agent"

    labels = {
        "approved_send": (
            "agent_approved_send",
            f"{actor} released outbound draft (simulated until email channel is wired).",
        ),
        "edited_send": (
            "agent_edited_send",
            f"{actor} released edited draft (simulated until email channel is wired).",
        ),
        "escalated_lead": (
            "agent_escalated_to_lead",
            f"{actor} escalated to Tech Lead — reason: {reason or 'n/a'}.",
        ),
    }
    action_type, detail = labels[decision]
    order = db.next_action_order(case_id)
    db.log_action(
        case_id,
        order,
        action_type,
        detail,
        {
            "decision": decision,
            "draft_chars": len(draft or ""),
            "reason": reason,
            "by": actor,
        },
    )

    if decision in ("approved_send", "edited_send"):
        db.log_message(case_id, draft or "", direction="outbound", channel="email")
        db.set_needs_review(case_id, False)
        db.set_case_status(case_id, db.STATUS_RELEASED, updated_by=actor)
        result["needs_review"] = False
        result["status"] = db.STATUS_RELEASED
    else:
        db.set_needs_review(case_id, True)
        db.set_case_status(
            case_id,
            db.STATUS_ESCALATED,
            updated_by=actor,
            escalate_reason=reason,
        )
        result["needs_review"] = True
        result["status"] = db.STATUS_ESCALATED
        result["escalate_reason"] = reason

    rem = dict(result.get("remediation") or {})
    steps = list(rem.get("steps") or [])
    steps.append(
        {
            "action_type": action_type,
            "detail": detail,
            "payload": {"decision": decision, "reason": reason, "by": actor},
        }
    )
    rem["steps"] = steps
    if decision == "edited_send":
        rem["email_draft"] = draft
    if decision in ("approved_send", "edited_send"):
        rem["steps"].append(
            {
                "action_type": "set_resolved_status",
                "detail": "Status → Released",
                "payload": {"status": db.STATUS_RELEASED, "resolved_status_log": True},
            }
        )
    result["remediation"] = rem
    result["agent_decision"] = decision
    result["status_updated_by"] = actor
    from workflows.outputs import build_case_outputs

    result["outputs"] = build_case_outputs(
        result.get("classification") or {},
        rem,
        needs_review=bool(result.get("needs_review")),
        case_id=case_id,
    )
    rem["outputs"] = result["outputs"]
    _toast_decision(decision, case_id)
    return result


def apply_lead_decision(
    result: dict[str, Any],
    decision: str,
    *,
    note: str = "",
    draft: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Log lead Acknowledge / Approve / Return / Note with status + reasons."""
    case_id = result.get("case_id") or ""
    if not case_id:
        return result

    user = current_user() or {}
    actor = user.get("name") or user.get("username") or "lead"

    labels = {
        "acknowledged": (
            "lead_acknowledged",
            f"{actor} acknowledged escalation — ownership taken.",
        ),
        "approved_release": (
            "lead_approved_release",
            f"{actor} approved release (simulated until email channel is wired).",
        ),
        "returned_to_agent": (
            "lead_returned_to_agent",
            f"{actor} returned to agent — reason: {reason or 'n/a'}.",
        ),
        "note": (
            "lead_note",
            f"{actor} note for agent: {(note or '').strip() or '(empty)'}",
        ),
    }
    if decision not in labels:
        return result

    action_type, detail = labels[decision]
    payload: dict[str, Any] = {
        "decision": decision,
        "role": "lead",
        "by": actor,
        "reason": reason,
    }
    if decision == "note":
        payload["note"] = note
    if decision == "returned_to_agent":
        payload["lead_note_to_agent"] = note
    order = db.next_action_order(case_id)
    db.log_action(case_id, order, action_type, detail, payload)

    if decision == "approved_release":
        body = draft or (result.get("remediation") or {}).get("email_draft") or ""
        db.log_message(case_id, body, direction="outbound", channel="email")
        db.set_needs_review(case_id, False)
        db.set_case_status(case_id, db.STATUS_RELEASED, updated_by=actor)
        result["needs_review"] = False
        result["status"] = db.STATUS_RELEASED
    elif decision == "returned_to_agent":
        db.set_needs_review(case_id, True)
        db.set_case_status(
            case_id,
            db.STATUS_RETURNED,
            updated_by=actor,
            return_reason=reason,
            lead_note_to_agent=note,
        )
        result["needs_review"] = True
        result["agent_decision"] = None
        result["status"] = db.STATUS_RETURNED
        result["return_reason"] = reason
        result["lead_note_to_agent"] = note
    elif decision == "note":
        db.set_case_status(
            case_id,
            str(result.get("status") or db.STATUS_ESCALATED),
            updated_by=actor,
            lead_note_to_agent=note,
        )
        result["lead_note_to_agent"] = note
    elif decision == "acknowledged":
        db.set_case_status(case_id, db.STATUS_ESCALATED, updated_by=actor)
        result["status"] = db.STATUS_ESCALATED

    rem = dict(result.get("remediation") or {})
    steps = list(rem.get("steps") or [])
    steps.append(
        {
            "action_type": action_type,
            "detail": detail,
            "payload": payload,
        }
    )
    if decision == "approved_release":
        steps.append(
            {
                "action_type": "set_resolved_status",
                "detail": "Status → Released (lead)",
                "payload": {"status": db.STATUS_RELEASED, "resolved_status_log": True},
            }
        )
    rem["steps"] = steps
    result["remediation"] = rem
    result["lead_decision"] = decision
    result["replay"] = False
    result["status_updated_by"] = actor
    from workflows.outputs import build_case_outputs

    result["outputs"] = build_case_outputs(
        result.get("classification") or {},
        rem,
        needs_review=bool(result.get("needs_review")),
        case_id=case_id,
    )
    rem["outputs"] = result["outputs"]
    _toast_decision(decision, case_id)
    return result


def case_is_open_escalation(result: dict[str, Any]) -> bool:
    """True when case is in escalated status awaiting lead resolution."""
    status = result.get("status")
    if status == db.STATUS_ESCALATED:
        return True
    if result.get("agent_decision") != "escalated_lead":
        return False
    lead = result.get("lead_decision")
    return lead not in ("approved_release", "returned_to_agent")


_AVATAR_COLORS = (
    "#2B6CB0",
    "#0F766E",
    "#B45309",
    "#475569",
    "#0369A1",
    "#3F6212",
    "#9A3412",
)


def _mail_initials(name: str) -> str:
    parts = [p for p in name.replace("_", " ").replace(".", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        token = parts[0]
        return token[:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _mail_avatar_color(seed: str) -> str:
    if not seed:
        return _AVATAR_COLORS[0]
    return _AVATAR_COLORS[sum(ord(c) for c in seed) % len(_AVATAR_COLORS)]


def _mail_when(iso: str | None) -> str:
    if not iso:
        return "—"
    raw = str(iso).replace("Z", "+00:00")
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(raw)
        return dt.strftime("%b %d")
    except ValueError:
        return str(iso)[:10]


def _case_from_label(case: dict[str, Any]) -> str:
    account = (case.get("account") or "").strip()
    if account and account.upper() not in {"UNKNOWN", "N/A", "NONE"}:
        return account
    assignee = (case.get("assigned_to") or "").strip()
    if assignee:
        return assignee
    subject = (case.get("subject") or "").strip()
    if subject:
        return subject.split()[0][:18]
    return "Customer"


def _case_body_preview(case: dict[str, Any], limit: int = 88) -> str:
    body = " ".join((case.get("body") or "").split())
    if not body:
        return "No message body"
    return body if len(body) <= limit else body[: limit - 1] + "…"


def mail_case_row_html(case: dict[str, Any], *, active: bool = False) -> str:
    """Email-client style row for one work-inbox case."""
    status = str(case.get("status") or db.STATUS_OPEN)
    status_label = db.STATUS_LABELS.get(status, status)
    from_label = _case_from_label(case)
    subject = (case.get("subject") or "Untitled request").strip()
    preview = _case_body_preview(case)
    branch = branch_label(str(case.get("request_type") or ""))
    when = _mail_when(case.get("received_at") or case.get("created_at"))
    sla = db.sla_remaining(case.get("sla_due_at"))
    unread = status in (db.STATUS_OPEN, db.STATUS_RETURNED) and not (
        case.get("assigned_to") or ""
    ).strip()
    sla_cls = "pd-mail-sla overdue" if "OVERDUE" in sla else "pd-mail-sla"
    sla_block = (
        f'<div class="{sla_cls}">{_esc_html(sla)}</div>' if sla and sla != "—" else ""
    )
    on = " on" if active else ""
    unread_cls = " unread" if unread else ""
    avatar = _mail_initials(from_label)
    color = _mail_avatar_color(from_label)
    return f"""
<div class="pd-mail-row{on}">
  <span class="pd-mail-dot{unread_cls}"></span>
  <span class="pd-mail-avatar" style="background:{color}">{_esc_html(avatar)}</span>
  <div class="pd-mail-body">
    <div class="pd-mail-top">
      <span class="pd-mail-from">{_esc_html(from_label)}</span>
      <span class="pd-mail-tag st-{_esc_html(status)}">{_esc_html(status_label)}</span>
      <span class="pd-mail-tag branch">{_esc_html(branch)}</span>
    </div>
    <div class="pd-mail-subline">
      <strong>{_esc_html(subject)}</strong>
      — {_esc_html(preview)}
    </div>
  </div>
  <div class="pd-mail-aside">
    <div class="pd-mail-time">{_esc_html(when)}</div>
    {sla_block}
  </div>
</div>
""".strip()


def render_mail_case_list(
    cases: list[dict[str, Any]],
    *,
    selected_id: str | None,
    key_prefix: str,
    title: str = "Inbox",
) -> str | None:
    """Mail-style inbox list. Returns a case_id when the agent opens a row."""
    st.markdown(
        f"""
<div class="pd-mail-head">
  <span class="title">{_esc_html(title)}</span>
  <span class="count">{len(cases)}</span>
</div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        "**Open** loads the case into the workbench on the right. "
        "**Claim** (below) assigns it to you — different action."
    )
    if not cases:
        st.markdown(
            '<div class="pd-mail-empty">No cases in this view.</div>',
            unsafe_allow_html=True,
        )
        return None

    clicked: str | None = None
    for case in cases:
        cid = str(case.get("case_id") or "")
        active = bool(selected_id and cid == selected_id)
        row, go = st.columns([0.82, 0.18], gap="small")
        with row:
            st.markdown(mail_case_row_html(case, active=active), unsafe_allow_html=True)
        with go:
            if st.button(
                "Open",
                key=f"{key_prefix}_{cid}",
                width="stretch",
                type="primary" if active else "secondary",
                help="Load this case into the workbench (subject, body, playbook result).",
            ):
                clicked = cid
    return clicked


def filter_cases_by_query(
    cases: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    if not q:
        return cases
    out: list[dict[str, Any]] = []
    for c in cases:
        blob = " ".join(
            str(c.get(k) or "")
            for k in (
                "case_id",
                "subject",
                "body",
                "account",
                "request_type",
                "status",
                "assigned_to",
            )
        ).lower()
        if q in blob:
            out.append(c)
    return out


def seed_work_inbox_if_empty() -> None:
    """One-time: run demo samples into the work queue as Unassigned."""
    if st.session_state.get("demo_seeded"):
        return
    if db.case_count() > 0:
        st.session_state.demo_seeded = True
        return
    from workflows.pipeline import process_request

    with st.spinner("Preparing work inbox from demo samples…"):
        for item in all_inbox_items():
            process_request(
                item.get("subject") or "",
                item.get("body") or "",
                request_id=str(item.get("id") or ""),
                assigned_to=None,
                actor="system",
            )
    st.session_state.demo_seeded = True


def open_case_in_workspace(case_id: str) -> bool:
    """Load a DB case into Process spine for active work (not audit-only)."""
    rebuilt = rebuild_result_from_case(case_id)
    if not rebuilt:
        return False
    case = db.get_case(case_id) or {}
    rebuilt["replay"] = False
    st.session_state.workspace_subject = case.get("subject") or ""
    st.session_state.workspace_body = case.get("body") or ""
    st.session_state.workspace_source_id = case_id
    st.session_state.selected_inbox_id = case_id
    st.session_state.last_result = rebuilt
    return True


def render_timeline_compact(result: dict[str, Any], heading: str) -> None:
    rem = result.get("remediation") or {}
    clf = result.get("classification") or {}
    steps = rem.get("steps") or []
    request_type = clf.get("request_type") or rem.get("branch") or ""
    parts = [
        f'<div class="pd-compare-col"><div class="hd">{heading}</div>',
        f'<div class="title">{branch_label(request_type)}</div>',
        f'<div class="pd-quiet">Case <span class="pd-mono">{result.get("case_id", "")}</span></div>',
    ]
    for i, step in enumerate(steps, start=1):
        if step.get("action_type") in (
            "agent_approved_send",
            "agent_edited_send",
            "agent_escalated_to_lead",
        ):
            continue
        parts.append(
            f'<div class="pd-compare-step"><span class="a">{i:02d} · '
            f'{step.get("action_type", "")}</span><br/>{step.get("detail", "")}</div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_branch_compare() -> None:
    """Side-by-side playbook timelines (dry run — not written to Case Log)."""
    from workflows.pipeline import process_request

    golden = [i for i in all_inbox_items() if i.get("lane") == "golden"]
    if len(golden) < 2:
        st.caption("Need at least two clear samples to compare.")
        return

    id_to_item = {i["id"]: i for i in golden}
    ids = [i["id"] for i in golden]
    labels = {
        i["id"]: f"{i['id']} · {branch_label(i.get('branch', ''))}" for i in golden
    }
    n = max(2, min(int(st.session_state.get("compare_slot_count") or 2), len(ids)))

    st.caption("Dry runs only — use Process → Run playbook to persist to Case Log.")
    c1, c2, c3 = st.columns([0.7, 0.7, 1.0])
    with c1:
        if st.button("Add", width="stretch", disabled=n >= len(ids), key="cmp_add"):
            st.session_state.compare_slot_count = n + 1
            st.session_state.compare_results = []
            st.rerun()
    with c2:
        if st.button("Remove", width="stretch", disabled=n <= 2, key="cmp_remove"):
            st.session_state.compare_slot_count = n - 1
            st.session_state.pop(f"compare_slot_{n - 1}_id", None)
            st.session_state.compare_results = []
            st.rerun()
    with c3:
        run_cmp = st.button("Compare", type="primary", width="stretch", key="cmp_run")

    picks: list[str] = []
    cols = st.columns(n)
    for i, col in enumerate(cols):
        with col:
            picks.append(
                st.selectbox(
                    f"Tab {i + 1}",
                    ids,
                    index=min(i, len(ids) - 1),
                    format_func=lambda x: labels[x],
                    key=f"compare_slot_{i}_id",
                )
            )

    if run_cmp:
        with st.spinner("Running playbooks…"):
            st.session_state.compare_results = [
                process_request(
                    id_to_item[rid].get("subject") or "",
                    id_to_item[rid].get("body") or "",
                    persist=False,
                )
                for rid in picks
            ]
            st.session_state.compare_result_labels = [
                labels.get(rid, rid) for rid in picks
            ]

    results = st.session_state.get("compare_results") or []
    result_labels = st.session_state.get("compare_result_labels") or []
    if results and len(results) == n:
        for tab, result, heading in zip(
            st.tabs([f"Tab {i + 1}" for i in range(n)]),
            results,
            result_labels or picks,
        ):
            with tab:
                render_timeline_compact(result, heading)


@st.dialog("Coach · compare playbook branches", width="large")
def open_branch_compare_dialog() -> None:
    """Training popup — how two playbooks differ (not a daily nav item)."""
    st.caption(
        "Show me how **Billing** vs **Outage** (or any two clear samples) differ — "
        "dry runs only, nothing written to Case Log."
    )
    render_branch_compare()
    if st.button("Close", width="stretch", key="cmp_close"):
        st.rerun()


def _esc_html(value: object) -> str:
    return html.escape(str(value if value not in (None, "") else "—"), quote=False)


def _toast_decision(kind: str, case_id: str) -> None:
    labels = {
        "escalated_lead": "Escalation (simulated)",
        "approved_send": "Release (simulated)",
        "edited_send": "Release (simulated)",
        "acknowledged": "Lead acknowledged (simulated)",
        "approved_release": "Lead approved release (simulated)",
        "returned_to_agent": "Returned to agent (simulated)",
        "note": "Lead note (simulated)",
    }
    st.toast(f"{labels.get(kind, kind)} · {case_id}")


def _case_outputs(result: dict[str, Any]) -> dict[str, Any]:
    outputs = result.get("outputs") or (result.get("remediation") or {}).get("outputs")
    if outputs:
        return outputs
    from workflows.outputs import build_case_outputs

    return build_case_outputs(
        result.get("classification") or {},
        result.get("remediation") or {},
        needs_review=bool(result.get("needs_review")),
        case_id=str(result.get("case_id") or ""),
    )


def render_toast_stack(result: dict[str, Any]) -> None:
    """Top alerts only — routine outputs stay in the ops pack."""
    outputs = _case_outputs(result)
    toasts: list[tuple[str, str, str, str]] = []

    if outputs.get("human_in_the_loop"):
        toasts.append(
            (
                "alert",
                "Hold",
                "Human review required",
                str(outputs.get("human_in_the_loop_flag") or "Hold outbound send"),
            )
        )
    if outputs.get("supervisor_alert"):
        toasts.append(
            (
                "alert",
                "Alert",
                "Supervisor alert (simulated)",
                str(outputs["supervisor_alert"]),
            )
        )
    sla = outputs.get("sla_flag")
    if isinstance(sla, dict):
        toasts.append(
            (
                "flag",
                "SLA",
                "SLA flag (simulated)",
                f"{sla.get('flag', 'SLA_ACTIVE')} · severity={sla.get('severity', '—')} · "
                f"{sla.get('hours', '—')}h · due {sla.get('due_at', '—')}",
            )
        )

    if not toasts:
        return

    cards = [
        f'<div class="pd-toast {variant}" style="animation-delay:{min(i * 0.04, 0.24):.2f}s">'
        f'<div class="kind">{kind}</div>'
        f'<div class="body"><strong>{_esc_html(title)}</strong>{_esc_html(body)}</div></div>'
        for i, (variant, kind, title, body) in enumerate(toasts)
    ]
    st.markdown(f'<div class="pd-toast-stack">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_outputs_pack(result: dict[str, Any]) -> None:
    """Brief-aligned generated outputs for ops reviewers."""
    outputs = _case_outputs(result)

    sla = outputs.get("sla_flag")
    if isinstance(sla, dict):
        sla_txt = (
            f"{sla.get('flag', 'SLA_ACTIVE')} · severity={sla.get('severity', '—')} · "
            f"{sla.get('hours', '—')}h · due {sla.get('due_at', '—')}"
        )
        sla_cls = "flag"
    else:
        sla_txt = "—"
        sla_cls = ""

    hitl = bool(outputs.get("human_in_the_loop"))
    hitl_cls = "warn" if hitl else "ok"
    status = str(outputs.get("resolved_status") or "—")
    if status in ("held_for_review", "open_escalated"):
        status_cls = "warn"
    elif status == "resolved":
        status_cls = "ok"
    else:
        status_cls = "flag"

    actions = outputs.get("action_summary") or []
    action_txt = " → ".join(str(a) for a in actions) if actions else "—"

    rows = [
        ("Classification", _esc_html(outputs.get("classification_label")), ""),
        ("Urgency", _esc_html(outputs.get("urgency")), "flag"),
        ("Action summary", _esc_html(action_txt), ""),
        (
            "Draft response",
            "See §5 draft above" if outputs.get("draft_response") else "—",
            "",
        ),
        (
            "Routing notification",
            _esc_html(
                (outputs.get("routing_notification") or "—")
                + (" (simulated)" if outputs.get("routing_notification") else "")
            ),
            "flag" if outputs.get("routing_notification") else "",
        ),
        (
            "Supervisor alert",
            _esc_html(
                (outputs.get("supervisor_alert") or "—")
                + (" (simulated)" if outputs.get("supervisor_alert") else "")
            ),
            "warn" if outputs.get("supervisor_alert") else "",
        ),
        (
            "Confirmation message",
            _esc_html(outputs.get("confirmation_message")),
            "",
        ),
        ("SLA flag", _esc_html(sla_txt + (" (simulated)" if sla_cls else "")), sla_cls),
        ("Follow-up task", _esc_html(outputs.get("follow_up_task")), ""),
        ("Human-in-the-loop", _esc_html(outputs.get("human_in_the_loop_flag")), hitl_cls),
        ("Resolved status log", _esc_html(status), status_cls),
        ("Case log entry", _esc_html(outputs.get("case_log_entry")), ""),
    ]
    body = "".join(
        f'<div class="pd-out-row"><div class="k">{k}</div>'
        f'<div class="v {cls}">{v}</div></div>'
        for k, v, cls in rows
    )
    st.markdown(
        f"""
<div class="pd-section">
  <div class="pd-section-title">Generated outputs · ops pack</div>
  <div class="pd-outputs">{body}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_result_spine(result: dict[str, Any]) -> None:
    """Linear post-run spine — Type → Why → Branch → Steps → Reply → Route → Log."""
    clf = result.get("classification") or {}
    rem = result.get("remediation") or {}
    steps = rem.get("steps") or []
    entities = clf.get("entities") or {}
    request_type = clf.get("request_type", "")
    confidence = float(clf.get("confidence") or 0)
    needs_review = bool(result.get("needs_review"))
    case_id = result.get("case_id", "")
    decision = result.get("agent_decision")
    lead_decision = result.get("lead_decision")
    is_replay = bool(result.get("replay"))
    role = active_role()
    is_agent = role == "agent"
    is_lead = role == "lead"
    open_escalation = case_is_open_escalation(result)
    case_status = result.get("status") or (
        db.STATUS_ON_HOLD if needs_review else db.STATUS_OPEN
    )
    status_label = db.STATUS_LABELS.get(case_status, case_status)
    status_by = result.get("status_updated_by") or "—"
    status_at = (result.get("status_updated_at") or "")[:19].replace("T", " ")
    lead_note = (result.get("lead_note_to_agent") or "").strip()
    return_reason = (result.get("return_reason") or "").strip()
    escalate_reason = (result.get("escalate_reason") or "").strip()

    if lead_note or return_reason:
        st.warning(
            f"**Lead returned this case**"
            + (f" — {return_reason}" if return_reason else "")
            + (f"\n\nNote for agent: {lead_note}" if lead_note else "")
        )

    if is_replay and is_agent and case_status not in (db.STATUS_RETURNED, db.STATUS_ON_HOLD):
        st.info(
            f"Case `{case_id}` from Case Log — audit view."
        )
    elif is_lead and open_escalation:
        st.info(
            f"Tech Lead · escalated `{case_id}`"
            + (f" — agent reason: {escalate_reason}" if escalate_reason else "")
            + ". Acknowledge / Approve release / Return."
        )

    # Critical hold alert only (before spine)
    if needs_review and not decision and is_agent:
        render_toast_stack(result)
    elif needs_review and open_escalation and is_lead:
        render_toast_stack(result)

    st.markdown(
        f"""
<div class="pd-section">
  <div class="pd-section-title">Case status</div>
  <div class="pd-chips">
    <span class="pd-chip type">{_esc_html(status_label)}</span>
    <span class="pd-chip">By {_esc_html(status_by)}</span>
    <span class="pd-chip">{_esc_html(status_at or '—')}</span>
    <span class="pd-chip">SLA { _esc_html(db.sla_remaining(result.get('sla_due_at'))) }</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    if lead_decision:
        lead_labels = {
            "acknowledged": "Lead acknowledged escalation",
            "approved_release": "Lead approved release (simulated until email wired)",
            "returned_to_agent": "Lead returned case to agent",
            "note": "Lead note logged",
        }
        st.markdown(
            f'<div class="pd-decision"><strong>Lead decision:</strong> '
            f'{lead_labels.get(lead_decision, lead_decision)}</div>',
            unsafe_allow_html=True,
        )
    elif decision:
        decision_labels = {
            "approved_send": "Released draft (simulated until email wired)",
            "edited_send": "Released edited draft (simulated until email wired)",
            "escalated_lead": "Escalated to Tech Lead — outbound held",
        }
        st.markdown(
            f'<div class="pd-decision"><strong>Agent decision:</strong> '
            f'{decision_labels.get(decision, decision)}</div>',
            unsafe_allow_html=True,
        )

    # 1) Classification + honesty lines
    review_chip = (
        '<span class="pd-chip review">Needs Review</span>' if needs_review else ""
    )
    forced = clf.get("forced_type")
    force_note = (
        f'<div class="pd-quiet">DEMO override — forced branch '
        f'<span class="pd-mono">{forced}</span>.</div>'
        if forced
        else ""
    )
    why_line = (
        f"Routed to **{branch_label(request_type)}** — "
        f"{(clf.get('rationale') or 'classifier match').split(';')[0][:180]}"
    )
    unsure_bits = []
    if needs_review:
        unsure_bits.append(
            f"Confidence {confidence:.0%} is below the {CONFIDENCE_REVIEW_THRESHOLD:.0%} review bar."
        )
    rat_l = str(clf.get("rationale") or "").lower()
    if any(x in rat_l for x in ("vague", "mixed", "ambigu", "margin")):
        unsure_bits.append("Intent looks mixed or vague — confirm before release.")
    unsure_line = " ".join(unsure_bits) or "No major uncertainty flags on this run."

    st.markdown(
        f"""
<div class="pd-section">
  <div class="pd-section-title">1 · Classification</div>
  <div class="pd-type">{branch_label(request_type)}</div>
  <div class="pd-chips">
    <span class="pd-chip type">{branch_label(request_type)}</span>
    <span class="pd-chip">Confidence {confidence:.0%}</span>
    <span class="pd-chip">Urgency {clf.get('urgency', '—')}</span>
    <span class="pd-chip">Sentiment {clf.get('sentiment', '—')}</span>
    {review_chip}
  </div>
  <div style="font-size:0.8rem;color:{MUTED};">
    Case <span class="pd-mono">{case_id}</span>
  </div>
  <div class="pd-body" style="margin-top:0.55rem;"><strong>Why this branch:</strong> {_esc_html(why_line.replace('**',''))}</div>
  <div class="pd-quiet"><strong>What I'm unsure about:</strong> {_esc_html(unsure_line)}</div>
  {force_note}
</div>
        """,
        unsafe_allow_html=True,
    )

    # 2) Why / rationale + entities
    entity_rows = []
    for k, title in (
        ("account", "Account"),
        ("amount", "Amount"),
        ("invoice", "Invoice"),
        ("plan", "Plan"),
        ("location", "Location"),
    ):
        if entities.get(k):
            entity_rows.append(
                f'<div class="k">{title}</div><div class="v">{entities[k]}</div>'
            )
    entities_html = (
        f'<div class="pd-section-title" style="margin-top:0.75rem;">Entities</div>'
        f'<div class="pd-dl">{"".join(entity_rows)}</div>'
        if entity_rows
        else ""
    )
    st.markdown(
        f"""
<div class="pd-section">
  <div class="pd-section-title">2 · Why / rationale</div>
  <div class="pd-body">{clf.get('rationale') or '—'}</div>
  {entities_html}
</div>
        """,
        unsafe_allow_html=True,
    )

    # 3) Branch map
    nodes = []
    for key, name, queue, _summary in PLAYBOOKS:
        on = "on" if key == request_type else ""
        nodes.append(
            f'<div class="pd-node {on}"><div class="nm">{name}</div>'
            f'<div class="q">{queue}</div></div>'
        )
    st.markdown(
        f"""
<div class="pd-section">
  <div class="pd-section-title">3 · Branch map</div>
  <div class="pd-branch">{"".join(nodes)}</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # 4) Remediation timeline + payload peek
    st.markdown(
        '<div class="pd-section"><div class="pd-section-title">4 · Remediation timeline</div></div>',
        unsafe_allow_html=True,
    )
    if not steps:
        st.caption("No actions logged.")
    for i, step in enumerate(steps, start=1):
        action = step.get("action_type", "action")
        detail = step.get("detail", "")
        payload = _payload_dict(step)
        with st.expander(f"{i:02d} · {action} — {detail[:80]}", expanded=False):
            st.markdown(f"**{action}**")
            st.write(detail)
            if payload:
                st.caption("Payload")
                st.json(payload)
            else:
                st.caption("No payload fields on this step.")

    # 5) Draft — locked until agent clicks Edit (Needs Review only)
    draft = rem.get("email_draft") or ""
    baseline_key = f"draft_baseline_{case_id}"
    edit_key = f"draft_edit_mode_{case_id}"
    view_key = f"draft_{case_id}_view"
    edit_buf_key = f"draft_{case_id}_edit"
    if baseline_key not in st.session_state:
        st.session_state[baseline_key] = draft
    if edit_key not in st.session_state:
        st.session_state[edit_key] = False

    editing = bool(st.session_state.get(edit_key)) and not decision
    # Agent edit gate only in agent role; lead always reads draft locked
    if is_lead:
        draft_locked = True
    elif is_agent and not is_replay and needs_review and not decision:
        draft_locked = not editing
    elif decision == "escalated_lead":
        draft_locked = True
    else:
        draft_locked = bool(decision)

    st.markdown(
        '<div class="pd-section"><div class="pd-section-title">5 · Draft customer response</div></div>',
        unsafe_allow_html=True,
    )
    if is_lead and open_escalation:
        st.caption("Draft locked for lead review — Approve release uses this draft (simulated until email wired).")
    elif is_agent and not is_replay and needs_review and not decision:
        if editing:
            st.caption("Editing unlocked — **Save** if needed, then **Release** or **Escalate** (reason required).")
        else:
            st.caption(
                "Draft locked. **Edit** to change it, **Release** (simulated until email wired), "
                "or **Escalate to lead** with a reason code."
            )

    # Remount widget when unlocking — same key stays disabled in Streamlit
    widget_key = edit_buf_key if editing else view_key
    if editing and edit_buf_key not in st.session_state:
        st.session_state[edit_buf_key] = (
            st.session_state.get(view_key)
            or result.get("draft_saved_text")
            or draft
        )
    if not editing and view_key not in st.session_state:
        st.session_state[view_key] = (
            result.get("draft_saved_text") or rem.get("email_draft") or draft
        )

    st.text_area(
        "Draft",
        height=220,
        key=widget_key,
        label_visibility="collapsed",
        disabled=draft_locked,
    )

    # Agent decision gate (agent role only) — includes Returned cases
    can_agent_act = (
        is_agent
        and not is_replay
        and needs_review
        and not decision
        and case_status in (db.STATUS_ON_HOLD, db.STATUS_RETURNED, db.STATUS_OPEN)
    )
    if can_agent_act:
        draft_now = st.session_state.get(widget_key) or draft
        baseline = st.session_state.get(baseline_key) or draft
        dirty = (draft_now or "").strip() != (baseline or "").strip()
        saved_text = result.get("draft_saved_text")
        unsaved = dirty and (
            saved_text is None
            or (draft_now or "").strip() != (saved_text or "").strip()
        )

        esc_reason = st.selectbox(
            "Escalate reason (required to escalate)",
            ESCALATE_REASONS,
            key=f"esc_reason_{case_id}",
        )

        g1, g2, g3, g4 = st.columns(4)
        with g1:
            send = st.button(
                "Release draft",
                type="primary",
                key=f"dec_send_{case_id}",
                width="stretch",
                help="Marks draft released (simulated until email is wired).",
            )
        with g2:
            edit = st.button(
                "Edit",
                key=f"dec_edit_{case_id}",
                width="stretch",
                disabled=editing,
                help="Unlock the AI draft for editing.",
            )
        with g3:
            can_save = bool(editing and unsaved)
            save = st.button(
                "Save",
                key=f"dec_save_{case_id}",
                width="stretch",
                disabled=not can_save,
                help="Save edits without releasing.",
            )
        with g4:
            escalate = st.button(
                "Escalate to lead",
                key=f"dec_esc_{case_id}",
                width="stretch",
                help="Requires a reason code.",
            )

        flash_key = f"draft_save_flash_{case_id}"
        if edit:
            st.session_state[edit_buf_key] = (
                st.session_state.get(view_key)
                or result.get("draft_saved_text")
                or draft
            )
            st.session_state[edit_key] = True
            st.session_state.pop(flash_key, None)
            st.rerun()
        if save and can_save:
            st.session_state.last_result = save_agent_draft(result, draft_now)
            st.session_state[flash_key] = True
            st.rerun()
        if send:
            working = result
            if editing and unsaved:
                working = save_agent_draft(result, draft_now)
            kind = "edited_send" if dirty else "approved_send"
            st.session_state[edit_key] = False
            st.session_state.pop(flash_key, None)
            st.session_state.last_result = apply_agent_decision(
                working, kind, draft_now
            )
            st.rerun()
        if escalate:
            if not esc_reason:
                st.error("Pick an escalate reason.")
            else:
                st.session_state[edit_key] = False
                st.session_state.pop(flash_key, None)
                st.session_state.last_result = apply_agent_decision(
                    result, "escalated_lead", draft_now, reason=esc_reason
                )
                st.rerun()

        if st.session_state.pop(flash_key, False):
            st.success("Draft saved — still held. Release or Escalate when ready.")
        elif editing and not unsaved and result.get("draft_saved"):
            st.caption("All changes saved.")
        elif editing and not dirty:
            st.caption("No changes yet — edit the draft to enable Save.")

    elif is_lead and open_escalation and case_id:
        st.markdown(
            '<div class="pd-section"><div class="pd-section-title">Lead actions</div></div>',
            unsafe_allow_html=True,
        )
        st.caption("Outbound release stays simulated until email is wired.")
        draft_now = st.session_state.get(widget_key) or draft
        ret_reason = st.selectbox(
            "Return reason (required to return)",
            RETURN_REASONS,
            key=f"ret_reason_{case_id}",
        )
        note_txt = st.text_area(
            "Note for agent (shown when returned)",
            key=f"lead_note_txt_{case_id}",
            height=80,
        )
        l1, l2, l3, l4 = st.columns(4)
        with l1:
            ack = st.button("Acknowledge", key=f"lead_ack_{case_id}", width="stretch")
        with l2:
            approve = st.button(
                "Approve release",
                type="primary",
                key=f"lead_approve_{case_id}",
                width="stretch",
            )
        with l3:
            ret = st.button("Return to agent", key=f"lead_return_{case_id}", width="stretch")
        with l4:
            note_btn = st.button("Save note", key=f"lead_note_btn_{case_id}", width="stretch")

        if ack:
            st.session_state.last_result = apply_lead_decision(result, "acknowledged")
            st.rerun()
        if approve:
            st.session_state.last_result = apply_lead_decision(
                result, "approved_release", draft=draft_now
            )
            st.rerun()
        if ret:
            if not ret_reason:
                st.error("Pick a return reason.")
            elif not (note_txt or "").strip():
                st.error("Add a short note the agent will see.")
            else:
                st.session_state.last_result = apply_lead_decision(
                    result,
                    "returned_to_agent",
                    reason=ret_reason,
                    note=note_txt,
                )
                st.rerun()
        if note_btn:
            st.session_state.last_result = apply_lead_decision(
                result, "note", note=note_txt or ""
            )
            st.rerun()

    elif not needs_review and not is_replay and not decision and is_agent:
        st.caption(
            f"Confidence ≥ {CONFIDENCE_REVIEW_THRESHOLD:.0%} — no hold. "
            "Draft logged for audit; high-confidence cases skip the release gate in this POC."
        )
    elif is_lead and not open_escalation:
        st.caption("Lead mode — open an Escalated case from your queue.")

    # 6) Routing + follow-up — ops truth
    follow = _follow_up_detail(steps)
    route_detail = _route_detail(rem, steps)
    pb = PLAYBOOK_BY_KEY.get(request_type)
    next_plain = (
        f"What happens next: {pb[3]}"
        if pb
        else f"What happens next: {rem.get('summary') or 'Follow the remediation timeline.'}"
    )
    sla_txt = db.sla_remaining(result.get("sla_due_at"))
    st.markdown(
        f"""
<div class="pd-section">
  <div class="pd-section-title">6 · Queue · ticket · follow-up</div>
  <div class="pd-callout-row">
    <div class="pd-callout">
      <div class="lbl">Queue</div>
      <div class="val">{rem.get('queue') or (pb[2] if pb else '—')}</div>
      <div class="sub">{route_detail}</div>
      <div class="sub">Ticket <span class="pd-mono">{rem.get('ticket_id') or '—'}</span></div>
    </div>
    <div class="pd-callout">
      <div class="lbl">Follow-up / SLA</div>
      <div class="val">{sla_txt}</div>
      <div class="sub">{follow}</div>
      <div class="sub">{_esc_html(next_plain)}</div>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # Ops pack + checklist after the linear spine body
    render_outputs_pack(result)
    flags = _outcome_flags(rem, steps, case_id)
    checks = [
        ("Response", flags["response"]),
        ("Route", flags["route"]),
        ("Follow-up", flags["follow_up"]),
        ("Log", flags["log"]),
    ]
    check_html = " · ".join(
        f'<span class="{"ok" if ok else "miss"}">{"✓" if ok else "○"} {label}</span>'
        for label, ok in checks
    )
    st.markdown(
        f'<div class="pd-section"><div class="pd-section-title">Outcome checklist</div>'
        f'<div class="pd-checklist">{check_html}</div></div>',
        unsafe_allow_html=True,
    )

    # 7) Case Log link
    persisted = result.get("persisted", True)
    if persisted is False:
        st.markdown(
            '<div class="pd-section"><div class="pd-section-title">7 · Case log</div>'
            '<div class="pd-body">Compare run — <strong>not persisted</strong> to Case Log.</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="pd-section"><div class="pd-section-title">7 · Case log</div>'
            f'<div class="pd-body">Persisted as <span class="pd-mono">{case_id}</span> '
            "— actions and messages are in Case Log.</div></div>",
            unsafe_allow_html=True,
        )
        if st.button("Open in Case Log", type="secondary", key=f"goto_log_{case_id}"):
            st.session_state.case_log_focus = case_id
            st.switch_page("pages/1_Case_Log.py")
