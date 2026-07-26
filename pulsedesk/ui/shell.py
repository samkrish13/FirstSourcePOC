"""Shared PulseDesk UI shell — ops workbench chrome.

Visual language: Zendesk / Freshdesk / ServiceNow Agent Workspace.
Metaphor: pick ticket → run playbook → everything is logged.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import streamlit as st

import db
from workflows.llm import (
    BRANCH_LABELS,
    CONFIDENCE_REVIEW_THRESHOLD,
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
        {**g, "lane": "golden"} for g in (data.get("golden") or [])
    ] + [
        {**e, "lane": "edge"} for e in (data.get("edge_cases") or [])
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
        "email": "p.sharma@pulsedesk.demo",
    },
    "r.mehta": {
        "username": "r.mehta",
        "name": "R. Mehta",
        "role": "lead",
        "initials": "RM",
        "password": "lead",
        "email": "r.mehta@pulsedesk.demo",
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
        "tour_closed": False,
        "tour_applied_step": -1,
        "tour_sample_case_id": None,
        "tour_sample_id": "REQ-001",
        "side_panel_action": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    _restore_login_from_url()


def _account_session_payload(account: dict[str, str]) -> dict[str, str]:
    return {
        "username": account["username"],
        "name": account["name"],
        "role": account["role"],
        "initials": account["initials"],
        "email": account.get("email") or f"{account['username']}@pulsedesk.demo",
    }


def _persist_login(username: str) -> None:
    """Keep desk login across browser refresh via URL (until Sign out)."""
    st.query_params["pd_user"] = username


def _clear_persisted_login() -> None:
    try:
        del st.query_params["pd_user"]
    except Exception:
        params = {k: v for k, v in st.query_params.items() if k != "pd_user"}
        st.query_params.clear()
        st.query_params.update(params)


def _restore_login_from_url() -> None:
    if isinstance(st.session_state.get("current_user"), dict):
        return
    username = str(st.query_params.get("pd_user") or "").strip()
    account = USERS.get(username)
    if account:
        st.session_state.current_user = _account_session_payload(account)


def current_user() -> dict[str, str] | None:
    user = st.session_state.get("current_user")
    return user if isinstance(user, dict) else None


def active_role() -> str:
    user = current_user()
    if user and user.get("role") in ROLE_PROFILES:
        return str(user["role"])
    return "agent"


def _find_user_by_login(email_or_user: str) -> dict[str, str] | None:
    key = (email_or_user or "").strip().lower()
    if not key:
        return None
    for account in USERS.values():
        if account["username"].lower() == key or account.get("email", "").lower() == key:
            return account
    return None


def _inject_login_css() -> None:
    """Narrow centered login. Constrains container & card width."""
    st.markdown(
        f"""
<style>
/* Kill sidebar + collapsed control on login (beats workbench force-open rules). */
.stApp:has(.pd-login-anchor) section[data-testid="stSidebar"],
.stApp:has(.pd-login-anchor) section[data-testid="stSidebar"][aria-expanded="false"],
.stApp:has(.pd-login-anchor) section[data-testid="stSidebar"][aria-expanded="true"],
.stApp:has(.pd-login-anchor) div[data-testid="stSidebarCollapsedControl"],
.stApp:has(.pd-login-anchor) [data-testid="stSidebarCollapseButton"],
.stApp:has(.pd-login-anchor) [data-testid="collapsedControl"] {{
  display: none !important;
  visibility: hidden !important;
  width: 0 !important;
  min-width: 0 !important;
  max-width: 0 !important;
  height: 0 !important;
  min-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  border: none !important;
  transform: none !important;
  position: fixed !important;
  left: -100vw !important;
  pointer-events: none !important;
  overflow: hidden !important;
}}
.stApp:has(.pd-login-anchor) [data-testid="stAppViewContainer"],
.stApp:has(.pd-login-anchor) [data-testid="stAppViewContainer"] > .main,
.stApp:has(.pd-login-anchor) section.main {{
  margin-left: 0 !important;
  left: 0 !important;
  width: 100% !important;
  max-width: 100% !important;
}}
header[data-testid="stHeader"] {{ display: none !important; }}

.stApp, [data-testid="stAppViewContainer"], section.main {{
  background: {BG} !important;
}}

/* Center and shrink main page container when on login page */
.stApp:has(.pd-login-anchor) .block-container,
div[data-testid="stAppViewContainer"]:has(.pd-login-anchor) .block-container,
section.main:has(.pd-login-anchor) .block-container,
[data-testid="stMainBlockContainer"]:has(.pd-login-anchor) {{
  max-width: 440px !important;
  width: min(440px, calc(100vw - 32px)) !important;
  margin-left: auto !important;
  margin-right: auto !important;
  padding: 48px 8px 40px !important;
}}

/* Login Card styling */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.pd-login-anchor) {{
  background: {SURFACE} !important;
  border: 1px solid {LINE} !important;
  border-radius: 16px !important;
  box-shadow: 0 12px 32px rgba(16, 24, 40, 0.06), 0 2px 6px rgba(16, 24, 40, 0.04) !important;
  padding: 32px 28px 24px !important;
  width: 100% !important;
  max-width: 440px !important;
  margin: 0 auto !important;
  box-sizing: border-box !important;
  overflow: hidden !important;
}}

div[data-testid="stVerticalBlockBorderWrapper"]:has(.pd-login-anchor) [data-testid="stForm"],
div[data-testid="stForm"] {{
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
}}

/* Hide "Press Enter to submit form" caption */
[data-testid="InputInstructions"],
div[data-testid="stForm"] [data-testid="stCaptionContainer"],
div[data-testid="stForm"] .stCaption {{
  display: none !important;
}}

.pd-login-hero {{
  text-align: center;
  margin: 0 0 20px;
  font-family: "IBM Plex Sans", system-ui, sans-serif;
}}
.pd-login-logo-row {{
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-bottom: 18px;
}}
.pd-login-dots {{
  display: grid;
  grid-template-columns: repeat(5, 3px);
  grid-template-rows: repeat(3, 3px);
  gap: 4px;
  opacity: 0.4;
}}
.pd-login-dots span {{
  width: 3px; height: 3px; border-radius: 50%; background: {MUTED};
}}
.pd-login-mark {{
  width: 48px; height: 48px; border-radius: 12px;
  background: {BRAND};
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.03em;
  display: inline-flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 18px rgba(43, 108, 176, 0.28);
}}
.pd-login-hero h1 {{
  margin: 0;
  color: {INK};
  font-size: 23px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
}}
.pd-login-or {{
  display: flex; align-items: center; gap: 12px;
  margin: 18px 0 15px;
  color: {MUTED};
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  font-family: "IBM Plex Sans", system-ui, sans-serif;
}}
.pd-login-or::before, .pd-login-or::after {{
  content: "";
  flex: 1;
  height: 1px;
  background: {LINE};
}}

div[data-testid="stForm"] [data-testid="stTextInput"] label,
div[data-testid="stForm"] [data-testid="stTextInput"] [data-testid="stWidgetLabel"] {{
  display: none !important;
}}
div[data-testid="stForm"] [data-testid="stTextInput"] input {{
  background-color: {SOFT} !important;
  color: {INK} !important;
  border: 1px solid {LINE} !important;
  border-radius: 10px !important;
  min-height: 44px !important;
  padding-left: 42px !important;
  font-family: "IBM Plex Sans", system-ui, sans-serif !important;
  font-size: 15px !important;
  transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}}
div[data-testid="stForm"] [data-testid="stTextInput"] input:focus {{
  border-color: {BRAND} !important;
  box-shadow: 0 0 0 3px rgba(43, 108, 176, 0.15) !important;
}}
div[data-testid="stForm"] [data-testid="stTextInput"] input::placeholder {{
  color: {MUTED} !important;
}}
div[data-testid="stForm"] input[aria-label="Email"] {{
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='18' height='18' fill='none' stroke='%235B6570' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='2' y='4' width='14' height='10' rx='2'/%3E%3Cpath d='m2 5 7 5 7-5'/%3E%3C/svg%3E") !important;
  background-repeat: no-repeat !important;
  background-position: 14px center !important;
  background-size: 18px !important;
}}
div[data-testid="stForm"] input[aria-label="Password"] {{
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='18' height='18' fill='none' stroke='%235B6570' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='4' y='8' width='10' height='8' rx='1.5'/%3E%3Cpath d='M6 8V6a3 3 0 0 1 6 0v2'/%3E%3C/svg%3E") !important;
  background-repeat: no-repeat !important;
  background-position: 14px center !important;
  background-size: 18px !important;
  padding-right: 44px !important;
}}

/* Single password box — strip stacked wrappers around the eye */
div[data-testid="stForm"] [data-testid="stTextInput"] [data-testid="stTextInputRootElement"],
div[data-testid="stForm"] [data-testid="stTextInput"] [data-baseweb="base-input"],
div[data-testid="stForm"] [data-testid="stTextInput"] [data-baseweb="input"] {{
  display: flex !important;
  align-items: center !important;
  background: {SOFT} !important;
  background-color: {SOFT} !important;
  border: 1px solid {LINE} !important;
  border-radius: 10px !important;
  box-shadow: none !important;
  outline: none !important;
  overflow: hidden !important;
  gap: 0 !important;
}}
div[data-testid="stForm"] [data-testid="stTextInput"] [data-testid="stTextInputRootElement"] > *,
div[data-testid="stForm"] [data-testid="stTextInput"] [data-baseweb="base-input"] > *,
div[data-testid="stForm"] [data-testid="stTextInput"] [data-baseweb="input"] > * {{
  background: transparent !important;
  background-color: transparent !important;
  border: none !important;
  box-shadow: none !important;
  outline: none !important;
}}
div[data-testid="stForm"] [data-testid="stTextInput"] input {{
  background: transparent !important;
  background-color: transparent !important;
  border: none !important;
  box-shadow: none !important;
  outline: none !important;
  border-radius: 0 !important;
  flex: 1 1 auto !important;
  min-width: 0 !important;
}}
div[data-testid="stForm"] [data-testid="stTextInput"] input:focus {{
  border: none !important;
  box-shadow: none !important;
  outline: none !important;
}}
div[data-testid="stForm"] [data-testid="stTextInput"] [data-testid="stTextInputRootElement"]:focus-within,
div[data-testid="stForm"] [data-testid="stTextInput"] [data-baseweb="base-input"]:focus-within,
div[data-testid="stForm"] [data-testid="stTextInput"] [data-baseweb="input"]:focus-within {{
  border-color: {BRAND} !important;
  box-shadow: 0 0 0 3px rgba(43, 108, 176, 0.15) !important;
}}
/* Eye button + every nested chrome around it */
div[data-testid="stForm"] [data-testid="stTextInput"] button,
div[data-testid="stForm"] [data-testid="stTextInput"] button *,
div[data-testid="stForm"] [data-testid="stTextInput"] button::before,
div[data-testid="stForm"] [data-testid="stTextInput"] button::after,
div[data-testid="stForm"] [data-testid="stTextInput"] [class*="StyledButton"],
div[data-testid="stForm"] [data-testid="stTextInput"] [data-testid="stTooltipHoverTarget"],
div[data-testid="stForm"] [data-testid="stTextInput"] [data-testid="stTooltipHoverTarget"] > div,
div[data-testid="stForm"] [data-testid="stTextInput"] [data-testid="stElementContainer"],
div[data-testid="stForm"] [data-testid="stTextInput"] [data-testid="stVerticalBlock"],
div[data-testid="stForm"] [data-testid="stTextInput"] [data-testid="column"],
div[data-testid="stForm"] [data-testid="stTextInput"] [data-testid="stHorizontalBlock"] {{
  background: transparent !important;
  background-color: transparent !important;
  background-image: none !important;
  border: none !important;
  box-shadow: none !important;
  outline: none !important;
}}
div[data-testid="stForm"] [data-testid="stTextInput"] button {{
  color: {MUTED} !important;
  min-height: 32px !important;
  max-height: 32px !important;
  height: 32px !important;
  width: 32px !important;
  min-width: 32px !important;
  padding: 0 !important;
  margin: 0 6px 0 0 !important;
  border-radius: 0 !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  position: relative !important;
  top: 0 !important;
  transform: none !important;
}}
div[data-testid="stForm"] [data-testid="stTextInput"] button:hover {{
  background: transparent !important;
  background-color: transparent !important;
  color: {INK} !important;
}}
div[data-testid="stForm"] [data-testid="stTextInput"] button svg,
div[data-testid="stForm"] [data-testid="stTextInput"] button [data-testid="stIconMaterial"],
div[data-testid="stForm"] [data-testid="stTextInput"] button span {{
  background: transparent !important;
  color: inherit !important;
  fill: currentColor !important;
  margin: 0 !important;
  padding: 0 !important;
  line-height: 1 !important;
}}

div[data-testid="stForm"] [data-testid="stFormSubmitButton"] button,
div[data-testid="stForm"] button[kind="primaryFormSubmit"],
div[data-testid="stForm"] button[data-testid="baseButton-primaryFormSubmit"],
div[data-testid="stForm"] button[kind="primary"] {{
  background: {BRAND} !important;
  border: none !important;
  border-radius: 10px !important;
  min-height: 44px !important;
  font-weight: 600 !important;
  font-size: 15px !important;
  font-family: "IBM Plex Sans", system-ui, sans-serif !important;
  box-shadow: 0 2px 4px rgba(43, 108, 176, 0.2) !important;
  margin-top: 8px !important;
  width: 100% !important;
}}
div[data-testid="stForm"] [data-testid="stFormSubmitButton"] button:hover {{
  background: #245a96 !important;
}}

div[data-testid="stVerticalBlockBorderWrapper"]:has(.pd-login-anchor) [data-testid="stButton"] button {{
  background: {SURFACE} !important;
  border: 1px solid {LINE} !important;
  border-radius: 10px !important;
  min-height: 42px !important;
  color: {INK} !important;
  font-size: 16px !important;
  font-weight: 600 !important;
  box-shadow: none !important;
  transition: all 0.15s ease !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.pd-login-anchor) [data-testid="stButton"] button:hover {{
  background: {SOFT} !important;
  border-color: #CBD5E1 !important;
}}

.pd-login-hint {{
  margin-top: 18px;
  padding: 12px;
  background: {SOFT};
  border: 1px solid {LINE};
  border-radius: 12px;
  margin-bottom: 20px;
  box-sizing: border-box;
  width: 100%;
}}
.pd-login-hint-header {{
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: {MUTED};
  margin-bottom: 9px;
}}
.pd-login-cred-card {{
  background: #FFFFFF;
  border: 1px solid {LINE};
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 7px;
}}
.pd-login-cred-card:last-child {{
  margin-bottom: 0;
}}
.pd-login-cred-top {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}}
.pd-login-badge {{
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}}
.pd-login-badge.agent {{
  background: #E0F2FE;
  color: #0369A1;
  border: 1px solid #BAE6FD;
}}
.pd-login-badge.lead {{
  background: #FEF3C7;
  color: #B45309;
  border: 1px solid #FDE68A;
}}
.pd-login-pass-pill {{
  font-size: 11px;
  color: {MUTED};
  background: {SOFT};
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid {LINE};
}}
.pd-login-pass-pill strong {{
  color: {INK};
  font-family: "IBM Plex Mono", monospace;
  font-weight: 600;
}}
.pd-login-email-text {{
  font-family: "IBM Plex Mono", monospace;
  font-size: 12px;
  color: {INK};
  word-break: break-all;
}}
</style>
        """,
        unsafe_allow_html=True,
    )


def _complete_login(account: dict[str, str]) -> None:
    st.session_state.current_user = _account_session_payload(account)
    _persist_login(account["username"])
    done = st.session_state.setdefault("tour_done", {})
    if not done.get(account["username"]):
        start_guided_tour()
    st.rerun()


def require_login() -> dict[str, str] | None:
    """Gate UI behind stub login. Returns user or None while login form is shown."""
    ensure_state()
    user = current_user()
    if user:
        return user

    _inject_login_css()

    with st.container(border=True):
        dots = "".join("<span></span>" for _ in range(15))
        st.markdown(
            f"""
<div class="pd-login-anchor">
  <div class="pd-login-hero">
    <div class="pd-login-logo-row">
      <div class="pd-login-dots">{dots}</div>
      <div class="pd-login-mark" aria-hidden="true">PD</div>
      <div class="pd-login-dots">{dots}</div>
    </div>
    <h1>Welcome Back</h1>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", border=False, clear_on_submit=False):
            email = st.text_input(
                "Email",
                placeholder="Email address",
                label_visibility="collapsed",
                key="login_email",
            )
            password = st.text_input(
                "Password",
                type="password",
                placeholder="Password",
                label_visibility="collapsed",
                key="login_password",
            )
            submitted = st.form_submit_button("Login", type="primary", width="stretch")

        if submitted:
            account = _find_user_by_login(email)
            if not (email or "").strip():
                st.error("Email required.")
                return None
            if not (password or "").strip():
                st.error("Password required.")
                return None
            if account and account.get("password") == password:
                _complete_login(account)
            st.error("Incorrect email or password.")

        st.markdown('<div class="pd-login-or">OR</div>', unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3, gap="small")
        with c1:
            apple = st.button("", width="stretch", key="oauth_apple")
        with c2:
            google = st.button("G", width="stretch", key="oauth_google")
        with c3:
            x_btn = st.button("𝕏", width="stretch", key="oauth_x")

        if apple or google or x_btn:
            st.info("Social login is not enabled in this demo — use email + password.")

        st.markdown(
            """
<div class="pd-login-hint">
  <div class="pd-login-hint-header">Demo Accounts</div>
  <div class="pd-login-cred-card">
    <div class="pd-login-cred-top">
      <span class="pd-login-badge agent">Agent</span>
      <span class="pd-login-pass-pill">Password: <strong>agent</strong></span>
    </div>
    <div class="pd-login-email-text">p.sharma@pulsedesk.demo</div>
  </div>
  <div class="pd-login-cred-card">
    <div class="pd-login-cred-top">
      <span class="pd-login-badge lead">Tech Lead</span>
      <span class="pd-login-pass-pill">Password: <strong>lead</strong></span>
    </div>
    <div class="pd-login-email-text">r.mehta@pulsedesk.demo</div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )
    return None


def logout() -> None:
    st.session_state.current_user = None
    st.session_state.last_result = None
    st.session_state.show_tour = False
    st.session_state.tour_closed = True
    _clear_persisted_login()
    st.rerun()


# Hands-on tour sample — first golden billing ticket
_TOUR_SAMPLE_ID = "REQ-001"
_PAGE_PROCESS = "pages/0_Process.py"
_PAGE_CASE_LOG = "pages/1_Case_Log.py"
_PAGE_PLAYBOOKS = "pages/2_Playbooks.py"


def _tour_sample_item() -> dict[str, Any] | None:
    sid = str(st.session_state.get("tour_sample_id") or _TOUR_SAMPLE_ID)
    for item in all_inbox_items():
        if str(item.get("id")) == sid:
            return item
    items = all_inbox_items()
    return items[0] if items else None


def _tour_steps_for(user: dict[str, str]) -> list[dict[str, Any]]:
    """Page-aware walkthrough steps. Each step can load sample data and switch pages."""
    name = user.get("name") or "you"
    sample = _tour_sample_item()
    sample_id = str((sample or {}).get("id") or _TOUR_SAMPLE_ID)
    sample_subj = str((sample or {}).get("subject") or "sample request")
    branch_key = str((sample or {}).get("branch") or "billing_dispute")
    branch_name = BRANCH_LABELS.get(branch_key, branch_key)
    case_id = st.session_state.get("tour_sample_case_id")

    if user.get("role") == "lead":
        return [
            {
                "title": "Welcome — Tech Lead walkthrough",
                "body": (
                    f"You are **{name}**. This short tour moves you across PulseDesk pages "
                    "the way a real lead works: **Process** (escalations) → **Case Log** "
                    "(audit) → **Playbooks** (what agents run)."
                ),
                "page": _PAGE_PROCESS,
                "badge": "Overview",
            },
            {
                "title": "Process · Escalated queue",
                "body": (
                    "On **Process**, the left rail only lists cases agents **escalated**. "
                    "Open one to review classification, timeline, and the draft. "
                    "Agent Edit / Release controls stay hidden on your account."
                ),
                "page": _PAGE_PROCESS,
                "action": "focus_escalated",
                "badge": "Process",
                "hint": "Left rail → Escalated. Pick a card, then use lead actions on the right.",
            },
            {
                "title": "Process · Lead actions",
                "body": (
                    "**Acknowledge** takes ownership. **Approve release** sends the reply "
                    "(simulated until email is wired). **Return to agent** needs a "
                    "**reason** plus a **note the agent will see** on the case."
                ),
                "page": _PAGE_PROCESS,
                "badge": "Process",
            },
            {
                "title": "Case Log · Full history",
                "body": (
                    "Every run is persisted here: status, assignment, actions, and messages. "
                    "Use **Replay on Process** when you want the spine back in the workbench."
                ),
                "page": _PAGE_CASE_LOG,
                "badge": "Case Log",
            },
            {
                "title": "Playbooks · Six branches",
                "body": (
                    "Agents run one of six remediation strategies per case. "
                    "Know these queues so escalations make sense when they land on your desk."
                ),
                "page": _PAGE_PLAYBOOKS,
                "badge": "Playbooks",
            },
            {
                "title": "You're ready",
                "body": (
                    "Back on **Process**, work the escalated queue. "
                    "Lifecycle: **Open → On hold → Escalated → Closed / Returned**."
                ),
                "page": _PAGE_PROCESS,
                "badge": "Done",
            },
        ]

    case_line = (
        f"Your tour case is **`{case_id}`** — it also appears in Case Log."
        if case_id
        else "After you run the sample, a real case id is written to Case Log."
    )
    return [
        {
            "title": "Welcome — work a real sample",
            "body": (
                f"You are **{name}**. This tour is hands-on: we load golden sample "
                f"**{sample_id}** ({branch_name}), run the playbook on **Process**, "
                "then open **Case Log** and **Playbooks** so you see how the desk fits together."
            ),
            "page": _PAGE_PROCESS,
            "badge": "Overview",
        },
        {
            "title": f"Process · Load sample {sample_id}",
            "body": (
                f"We just placed **{sample_id}** into the workbench:\n\n"
                f"> {sample_subj}\n\n"
                "Look at **Subject** and **Message body** on the right — same fields you'd "
                "get from Gmail sync, Compose, or **Load demo sample**. "
                "Left rail is your work inbox (Mine / Unassigned / All)."
            ),
            "page": _PAGE_PROCESS,
            "action": "load_sample",
            "badge": "Process",
            "hint": "Right panel shows the sample ticket. Next step runs the playbook on it.",
        },
        {
            "title": "Process · Run the playbook",
            "body": (
                f"PulseDesk will classify this as **{branch_name}**, build a draft reply, "
                "and log every step. Low confidence parks the case **On hold / Needs Review**.\n\n"
                "Use **Run sample now** below (same as the **Run playbook** button on the page)."
            ),
            "page": _PAGE_PROCESS,
            "action": "ensure_sample_loaded",
            "badge": "Process",
            "cta": "run_sample",
            "hint": "After it runs, scroll the result spine under the form.",
        },
        {
            "title": "Process · Read your result",
            "body": (
                f"{case_line}\n\n"
                "On the page behind this dialog: **Why this branch**, "
                "**What I'm unsure about**, the action timeline, the draft, then "
                "**Queue · ticket · follow-up**. That spine is what you hand to a lead or customer."
            ),
            "page": _PAGE_PROCESS,
            "action": "ensure_sample_run",
            "badge": "Process",
            "hint": "Scroll the Process main column to review the live spine.",
        },
        {
            "title": "Process · Finish the ticket",
            "body": (
                "When you're ready to act: **Edit → Save → Release draft**, or "
                "**Escalate to lead** with a reason code. "
                "You can also **Claim** Unassigned inbox rows, **Sync Gmail**, or "
                "**Coach: compare** two playbooks without writing Case Log."
            ),
            "page": _PAGE_PROCESS,
            "badge": "Process",
        },
        {
            "title": "Case Log · Your sample is saved",
            "body": (
                f"Open the case we just created"
                + (f" (**`{case_id}`**)" if case_id else "")
                + ". Inspect actions and messages — this is the audit trail interviewers "
                "and leads care about. **Replay on Process** brings it back to the workbench."
            ),
            "page": _PAGE_CASE_LOG,
            "action": "focus_tour_case",
            "badge": "Case Log",
        },
        {
            "title": f"Playbooks · {branch_name} and the other five",
            "body": (
                f"Your sample used the **{branch_name}** branch. This page lists all six "
                "strategies (queue, steps, outputs). Process picks one per case; "
                "Case Log stores what actually ran."
            ),
            "page": _PAGE_PLAYBOOKS,
            "badge": "Playbooks",
        },
        {
            "title": "You're ready to work",
            "body": (
                f"Back on **Process** with **{sample_id}** still in context. "
                "Try another sample from **Load demo sample**, claim an inbox case, "
                "or connect Gmail. Replay this tour anytime from the profile menu."
            ),
            "page": _PAGE_PROCESS,
            "badge": "Done",
        },
    ]


def _apply_tour_action(action: str | None, user: dict[str, str]) -> None:
    """Side effects when a tour step becomes active (load sample, run, focus case)."""
    if not action:
        return
    if action in ("load_sample", "ensure_sample_loaded"):
        item = _tour_sample_item()
        if not item:
            return
        # Don't wipe a live tour result when merely ensuring the form is filled
        if action == "ensure_sample_loaded" and st.session_state.get("tour_sample_case_id"):
            return
        if action == "load_sample" or not (
            st.session_state.get("workspace_subject") or ""
        ).strip():
            open_in_workspace(item)
            st.session_state._pending_inbox_filter = "All"
            if "mailbox_view_filter" in st.session_state:
                st.session_state._pending_mailbox_view = "All mailboxes"
        return

    if action == "ensure_sample_run":
        if not st.session_state.get("tour_sample_case_id"):
            _tour_run_sample(user)
        return

    if action == "focus_tour_case":
        cid = st.session_state.get("tour_sample_case_id")
        if cid:
            st.session_state.case_log_focus = cid
        return

    if action == "focus_escalated":
        rows = db.list_escalated_cases(limit=1)
        if rows:
            cid = str(rows[0].get("case_id") or "")
            if cid and open_case_in_workspace(cid):
                st.session_state.lead_queue_focus = cid
        return


def _tour_run_sample(user: dict[str, str]) -> dict[str, Any] | None:
    """Run the loaded tour sample through the real playbook pipeline."""
    from workflows.pipeline import process_request

    item = _tour_sample_item()
    subject = (st.session_state.get("workspace_subject") or "").strip()
    body = (st.session_state.get("workspace_body") or "").strip()
    if not body and item:
        open_in_workspace(item)
        subject = (item.get("subject") or "").strip()
        body = (item.get("body") or "").strip()
    if not body:
        return None

    sample_id = str((item or {}).get("id") or _TOUR_SAMPLE_ID)
    result = process_request(
        subject or "(no subject)",
        body,
        assigned_to=user.get("username"),
        actor=user.get("name") or "tour",
    )
    case_id = str(result.get("case_id") or "")
    st.session_state.last_result = result
    st.session_state.workspace_source_id = case_id
    st.session_state.selected_inbox_id = case_id
    st.session_state.tour_sample_case_id = case_id
    st.session_state.case_log_focus = case_id
    st.session_state.tour_sample_id = sample_id
    return result


def _go_tour_step(new_step: int, user: dict[str, str]) -> None:
    steps = _tour_steps_for(user)
    n = len(steps)
    new_step = max(0, min(int(new_step), n - 1))
    st.session_state.tour_step = new_step
    st.session_state.tour_applied_step = -1
    st.session_state.show_tour = True
    page = steps[new_step].get("page")
    if page:
        st.switch_page(str(page))
    st.rerun()


def _finish_tour(username: str) -> None:
    """Close tour permanently for this user (until Take tour is chosen)."""
    st.session_state.show_tour = False
    st.session_state.tour_step = 0
    st.session_state.tour_applied_step = -1
    st.session_state.tour_closed = True
    done = st.session_state.setdefault("tour_done", {})
    if username:
        done[username] = True


def start_guided_tour(*, switch_to_process: bool = False) -> None:
    """Open / restart the first-time user tour on Process with a fresh sample path."""
    st.session_state.tour_closed = False
    st.session_state.show_tour = True
    st.session_state.tour_step = 0
    st.session_state.tour_applied_step = -1
    st.session_state.tour_sample_case_id = None
    st.session_state.tour_sample_id = _TOUR_SAMPLE_ID
    if switch_to_process:
        st.switch_page(_PAGE_PROCESS)


def render_guided_tour_if_needed() -> None:
    """In-page tour card — never use st.dialog (dialogs reopen on every widget click)."""
    user = current_user() or {}
    username = str(user.get("username") or "")
    done = st.session_state.setdefault("tour_done", {})

    if st.session_state.get("tour_closed"):
        st.session_state.show_tour = False
        return
    if done.get(username) and not st.session_state.get("show_tour"):
        return
    if not st.session_state.get("show_tour"):
        return

    steps = _tour_steps_for(user)
    n = len(steps)
    step = int(st.session_state.get("tour_step") or 0)
    step = max(0, min(step, n - 1))
    spec = steps[step]

    badge = spec.get("badge") or ""
    with st.container(border=True):
        st.markdown("##### PulseDesk guided tour")
        st.progress(
            (step + 1) / n, text=f"Step {step + 1} of {n} · {badge}".strip(" ·")
        )
        st.markdown(f"### {spec['title']}")
        st.markdown(str(spec.get("body") or ""))
        if spec.get("hint"):
            st.info(spec["hint"])

        item = _tour_sample_item()
        if item and user.get("role") != "lead":
            branch = BRANCH_LABELS.get(str(item.get("branch") or ""), item.get("branch"))
            case_id = st.session_state.get("tour_sample_case_id")
            st.markdown(
                f'<div class="pd-tour-sample">'
                f'<span class="tag">Sample</span> '
                f'<strong>{_esc_html(item.get("id"))}</strong> · {_esc_html(branch)}'
                + (
                    f' · case <code>{_esc_html(case_id)}</code>'
                    if case_id
                    else ""
                )
                + f'<div class="subj">{_esc_html(item.get("subject") or "")}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )

        if spec.get("cta") == "run_sample":
            already = bool(st.session_state.get("tour_sample_case_id"))
            if already:
                st.success(
                    f"Sample already run → **{st.session_state.tour_sample_case_id}**. "
                    "Continue to read the spine, or run again."
                )
            run_label = "Run sample again" if already else "Run sample now"
            if st.button(
                run_label, type="primary", width="stretch", key="tour_run_sample"
            ):
                with st.spinner("Running playbook on sample…"):
                    result = _tour_run_sample(user)
                if result:
                    st.session_state.tour_step = min(step + 1, n - 1)
                    st.session_state.tour_applied_step = -1
                    st.rerun()
                else:
                    st.error("Could not run sample — load a demo sample first.")

        st.caption("Replay anytime from the profile menu → **Take tour**. Use **Skip tour** to dismiss.")

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("Back", width="stretch", disabled=step <= 0, key="tour_back"):
                _go_tour_step(step - 1, user)
        with b2:
            if st.button("Skip tour", width="stretch", key="tour_skip"):
                _finish_tour(username)
                st.rerun()
        with b3:
            if step >= n - 1:
                if st.button(
                    "Finish", type="primary", width="stretch", key="tour_finish"
                ):
                    _finish_tour(username)
                    st.switch_page(_PAGE_PROCESS)
            elif st.button("Next", type="primary", width="stretch", key="tour_next"):
                if spec.get("cta") == "run_sample" and not st.session_state.get(
                    "tour_sample_case_id"
                ):
                    _tour_run_sample(user)
                _go_tour_step(step + 1, user)



def prepare_tour_workspace() -> None:
    """Apply the active tour step's sample/page side effects before page widgets render."""
    if st.session_state.get("tour_closed") or not st.session_state.get("show_tour"):
        return
    user = current_user()
    if not user:
        return
    steps = _tour_steps_for(user)
    if not steps:
        return
    step = int(st.session_state.get("tour_step") or 0)
    step = max(0, min(step, len(steps) - 1))
    applied = int(st.session_state.get("tour_applied_step", -1))
    if applied == step:
        return
    _apply_tour_action(steps[step].get("action"), user)
    st.session_state.tour_applied_step = step


def render_mailbox_connect_panel(*, actor: str | None = None) -> None:
    """In-app Gmail connect: invite → help for app password → verify / revoke / remove."""
    from integrations.gmail_inbox import complete_mailbox_auth

    st.markdown("##### Connect a mailbox")
    st.caption(
        "Mailboxes only sync after authentication here. "
        "Send an invite → follow **How to get an App Password** → paste it → Verify. "
        "You can revoke an invite or remove an address at any time."
    )

    with st.expander("How to get a Google App Password (help)", expanded=False):
        st.markdown(
            """
**Do this while signed into the Gmail you invited.**

1. Open **[Google Account → App passwords](https://myaccount.google.com/apppasswords)**  
   (If the page says unavailable: turn on **2-Step Verification** first under Security, then return.)
2. Under **Select app**, choose **Mail** (or Other → type `PulseDesk`).
3. Click **Generate**. Copy the **16-character** password (spaces are fine).
4. Back in PulseDesk, open the invite card → paste it → **Verify & connect**.

**Notes**
- Use an **App Password**, not your normal Gmail login password.
- App Passwords only appear after 2-Step Verification is on.
- If login still fails, revoke the invite, create a new App Password, and invite again.
            """
        )

    rows = db.list_linked_mailbox_rows()
    focus_help = st.session_state.pop("mailbox_help_focus", None)

    if rows:
        for row in rows:
            status = str(row.get("status") or "")
            label = db.MAILBOX_STATUS_LABELS.get(status, status)
            tone = {
                db.MAILBOX_CONNECTED: "ok",
                db.MAILBOX_INVITED: "warn",
                db.MAILBOX_FAILED: "bad",
            }.get(status, "muted")
            mid = str(row["id"])
            addr = str(row.get("address") or "")
            st.markdown(
                f"""
<div class="pd-mb-card">
  <div class="pd-mb-top">
    <strong>{_esc_html(row.get("label") or "")}</strong>
    <span class="pd-mb-addr">{_esc_html(addr)}</span>
  </div>
  <div class="pd-mb-status {tone}">{_esc_html(label)}</div>
  <div class="pd-mb-detail">{_esc_html(row.get("status_detail") or "")}</div>
</div>
                """,
                unsafe_allow_html=True,
            )

            # Always offer help + remove; invite/failed also get auth + revoke
            help_open = focus_help == mid or status == db.MAILBOX_FAILED
            with st.expander(f"Help · App Password for {addr}", expanded=help_open):
                st.markdown(
                    f"""
Signed into **`{addr}`**:

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Enable **2-Step Verification** if Google asks
3. Generate an app password named **PulseDesk**
4. Paste the 16 characters in **Complete authentication** below
                    """
                )
                st.link_button(
                    "Open Google App Passwords",
                    "https://myaccount.google.com/apppasswords",
                    width="stretch",
                )

            if status in (db.MAILBOX_INVITED, db.MAILBOX_FAILED):
                with st.expander(
                    f"Complete authentication · {addr}",
                    expanded=(status == db.MAILBOX_FAILED or focus_help == mid),
                ):
                    pwd = st.text_input(
                        "App password",
                        type="password",
                        key=f"mb_pwd_{mid}",
                        placeholder="xxxx xxxx xxxx xxxx",
                    )
                    if st.button(
                        "Verify & connect",
                        type="primary",
                        width="stretch",
                        key=f"mb_verify_{mid}",
                        disabled=bool(st.session_state.get(f"_mb_busy_{mid}")),
                    ):
                        cleaned = "".join((pwd or "").split())
                        if len(cleaned) < 8:
                            st.warning("Paste a Google App Password (16 characters) before verifying.")
                        else:
                            st.session_state[f"_mb_busy_{mid}"] = True
                            with st.spinner("Verifying with Gmail…"):
                                ok, msg = complete_mailbox_auth(mid, cleaned)
                            st.session_state.pop(f"_mb_busy_{mid}", None)
                            if ok:
                                st.success(msg)
                                st.rerun()
                            st.error(msg)

                a1, a2 = st.columns(2)
                with a1:
                    if st.button(
                        "Revoke invitation",
                        width="stretch",
                        key=f"mb_revoke_{mid}",
                        help="Cancel this invite. The address is removed until you invite again.",
                    ):
                        db.delete_mailbox(mid)
                        st.toast(f"Invitation revoked for {addr}")
                        st.rerun()
                with a2:
                    if st.button(
                        "Remove address",
                        width="stretch",
                        key=f"mb_remove_{mid}",
                        help="Delete this mailbox from PulseDesk.",
                    ):
                        db.delete_mailbox(mid)
                        st.toast(f"Removed {addr}")
                        st.rerun()
            else:
                # Connected (or other) — allow remove / disconnect
                b1, b2 = st.columns(2)
                with b1:
                    if st.button(
                        "Remove address",
                        width="stretch",
                        key=f"mb_remove_{mid}",
                        help="Disconnect and delete this mailbox from PulseDesk.",
                    ):
                        db.delete_mailbox(mid)
                        st.toast(f"Removed {addr}")
                        st.rerun()
                with b2:
                    if st.button(
                        "Show App Password help",
                        width="stretch",
                        key=f"mb_help_btn_{mid}",
                    ):
                        st.session_state.mailbox_help_focus = mid
                        st.rerun()

    with st.form("mailbox_invite_form", clear_on_submit=True):
        st.markdown("**Send connection invite**")
        address = st.text_input(
            "Gmail address",
            placeholder="care@yourdomain.com or name@gmail.com",
        )
        label = st.text_input("Display name (optional)", placeholder="Ops inbox")
        submitted = st.form_submit_button(
            "Send invitation", type="primary", width="stretch"
        )
    if submitted:
        addr = (address or "").strip()
        if not addr or "@" not in addr:
            st.warning("Enter a valid Gmail address before sending an invite.")
        else:
            try:
                invited = db.invite_mailbox(
                    addr, label=(label or "").strip() or None, invited_by=actor
                )
                st.session_state.mailbox_help_focus = invited["id"]
                st.success(
                    f"Invitation sent to **{invited['address']}**. "
                    "Use **Help · App Password** on that card, then paste the password to verify."
                )
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not create invite: {exc}")


def clear_draft_keys() -> None:
    """Drop §5 draft widget session keys so editors remount cleanly."""
    for k in list(st.session_state.keys()):
        sk = str(k)
        if sk.startswith(
            (
                "draft_edit_mode_",
                "draft_baseline_",
                "draft_gen_",
                "draft_active_buf_",
                "draft_save_flash_",
            )
        ):
            st.session_state.pop(k, None)
            continue
        if not sk.startswith("draft_"):
            continue
        rest = sk[len("draft_") :]
        if rest.endswith(("_view", "_edit")) or "_e" in rest:
            st.session_state.pop(k, None)


def compose_new_request() -> None:
    """Blank Process form for freeform classification demos."""
    st.session_state.workspace_subject = ""
    st.session_state.workspace_body = ""
    st.session_state.workspace_source_id = "manual:compose"
    st.session_state.last_result = None
    st.session_state.pop("replay_banner", None)
    clear_draft_keys()


def open_in_workspace(item: dict[str, Any]) -> None:
    st.session_state.selected_inbox_id = item["id"]
    st.session_state.workspace_source_id = item["id"]
    st.session_state.workspace_subject = item.get("subject") or ""
    body = str(item.get("body") or "")
    from_addr = str(item.get("from") or "").strip()
    if from_addr and not re.search(r"(?im)^From:\s*", body):
        body = f"From: {from_addr}\n\n{body}".strip()
    st.session_state.workspace_body = body
    st.session_state.last_result = None
    st.session_state.pop("replay_banner", None)
    clear_draft_keys()


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
section.main > div {{ max-width: 100% !important; width: 100% !important; }}
div[data-testid="stAppViewContainer"] {{
  width: 100% !important;
}}
div[data-testid="stAppViewContainer"] > .main {{
  overflow-x: hidden;
  width: 100% !important;
}}
div[data-testid="stMainBlockContainer"],
section.main .block-container,
.stMain .block-container {{
  max-width: 100% !important;
  width: 100% !important;
  padding: 8px 20px 24px 20px !important;
}}
#MainMenu, footer {{ visibility: hidden; }}
/* Desktop / login: hide Streamlit chrome. Mobile (logged-in) keeps a slim header for the nav toggle. */
@media (min-width: 901px) {{
  header[data-testid="stHeader"],
  div[data-testid="stToolbar"],
  div[data-testid="stDecoration"],
  [data-testid="stAppToolbar"],
  .stAppHeader {{
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
  }}
}}
.stApp:has(.pd-login-anchor) header[data-testid="stHeader"],
.stApp:has(.pd-login-anchor) div[data-testid="stToolbar"],
.stApp:has(.pd-login-anchor) div[data-testid="stDecoration"],
.stApp:has(.pd-login-anchor) [data-testid="stAppToolbar"],
.stApp:has(.pd-login-anchor) .stAppHeader {{
  display: none !important;
  height: 0 !important;
  min-height: 0 !important;
}}

/* Desktop: keep workbench nav permanently expanded (not on login). */
@media (min-width: 901px) {{
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"],
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"][aria-expanded="false"] {{
    display: flex !important;
    visibility: visible !important;
    min-width: 264px !important;
    width: 264px !important;
    max-width: 264px !important;
    height: 100vh !important;
    max-height: 100vh !important;
    background: #FFFFFF !important;
    border-right: 1px solid #E2E8F0 !important;
    box-shadow: 1px 0 4px rgba(0, 0, 0, 0.03) !important;
    position: relative !important;
    z-index: 90 !important;
    padding: 0 !important;
    margin: 0 !important;
    margin-left: 0 !important;
    left: 0 !important;
    top: 0 !important;
    transform: none !important;
    overflow: hidden !important;
  }}

  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] button[kind="header"],
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"],
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="collapsedControl"],
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="stSidebarHeader"],
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] header,
  .stApp:not(:has(.pd-login-anchor)) div[data-testid="stSidebarCollapsedControl"],
  .stApp:not(:has(.pd-login-anchor)) [data-testid="stSidebarCollapseButton"] {{
    display: none !important;
    visibility: hidden !important;
    width: 0 !important;
    height: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
  }}
}}

/* Shared sidebar chrome (desktop + mobile when open) */
.stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] > div:first-child,
.stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
  background: #FFFFFF !important;
  height: 100% !important;
  max-height: 100vh !important;
  padding: 0 !important;
  margin: 0 !important;
  overflow: hidden !important;
}}

.stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
  background: #FFFFFF !important;
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
  max-height: 100vh !important;
  box-sizing: border-box !important;
  padding: 14px 12px !important;
  margin: 0 !important;
  overflow: hidden !important;
}}

/* Only the top-level sidebar column fills height — nested blocks stay compact */
.stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div {{
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
  flex: 1 1 auto !important;
  min-height: 0 !important;
  gap: 0 !important;
}}
.stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]
  > div > div[data-testid="stVerticalBlock"] {{
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
  flex: 1 1 auto !important;
  min-height: 0 !important;
  gap: 0 !important;
}}
.stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]
  div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"] {{
  height: auto !important;
  flex: 0 0 auto !important;
  min-height: 0 !important;
  gap: 0 !important;
}}

.stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="stElementContainer"],
.stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] .element-container {{
  width: 100% !important;
  margin: 0 !important;
  padding: 0 !important;
  flex: 0 0 auto !important;
  height: auto !important;
  min-height: 0 !important;
}}

/* Brand Card */
.pd-side-brand-card {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 2px 4px 12px;
  margin-bottom: 6px;
  border-bottom: 1px solid #EAECF0;
}}
.pd-side-logo-mark {{
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: {BRAND};
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: none;
}}
.pd-side-brand-meta {{
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}}
.pd-side-brand-meta .title-row {{
  display: flex;
  align-items: center;
  gap: 8px;
}}
.pd-side-brand-meta .brand-title {{
  font-family: "IBM Plex Sans", system-ui, sans-serif;
  font-weight: 700;
  font-size: 16px;
  color: #101828;
  letter-spacing: -0.02em;
  line-height: 1.2;
}}
.pd-side-brand-meta .badge-env {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.01em;
  color: #667085;
  background: transparent;
  border: none;
  padding: 0;
  text-transform: none;
  flex-shrink: 0;
  line-height: 1;
}}
.pd-side-brand-meta .badge-env::before {{
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #98A2B3;
  flex-shrink: 0;
}}
.pd-side-brand-meta .badge-env.connected {{
  color: #475467;
}}
.pd-side-brand-meta .badge-env.connected::before {{
  background: #12B76A;
}}
.pd-side-brand-meta .badge-env.demo::before {{
  background: #98A2B3;
}}
.pd-side-brand-meta .brand-sub {{
  font-size: 11px;
  font-weight: 500;
  color: #667085;
  margin-top: 2px;
}}

/* Nav Label */
.pd-side-nav-label {{
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: {MUTED};
  padding: 2px 9px 4px;
  text-transform: uppercase;
  margin-bottom: 10px;
}}

/* Reserve space so nav never sits under the pinned account dock */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
  padding-bottom: 140px !important;
}}

/*
 * Pin profile + actions to the sidebar bottom.
 * The account block is always the last child of the root sidebar column.
 * Avoid broad :has(.pd-side-footer-dock) — it also matches the root column.
 */
section[data-testid="stSidebar"]
  [data-testid="stSidebarUserContent"]
  > div
  > div[data-testid="stVerticalBlock"]
  > :last-child {{
  position: fixed !important;
  left: 12px !important;
  bottom: 12px !important;
  width: calc(264px - 24px) !important;
  max-width: calc(264px - 24px) !important;
  margin: 0 !important;
  padding: 11px 0 0 0 !important;
  border-top: 1px solid {LINE} !important;
  background: #FFFFFF !important;
  z-index: 100 !important;
  box-sizing: border-box !important;
  height: auto !important;
  flex: 0 0 auto !important;
}}
.pd-side-footer-dock {{
  padding: 0;
  margin: 0 0 7px 0;
}}
.pd-side-user-card {{
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 2px 2px 2px;
  min-width: 0;
  margin-bottom:20px;
}}
.pd-side-user-card .user-info {{
  min-width: 0;
  flex: 1;
  overflow: hidden;
}}
.pd-side-user-card .user-name {{
  font-weight: 600;
  font-size: 13px;
  color: {INK};
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.pd-side-user-card .user-role {{
  font-size: 11px;
  color: {MUTED};
  margin-top: 1px;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}

/* Nav links — tight stack, no stretch gaps */
section[data-testid="stSidebar"] [data-testid="stPageLink"],
section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {{
  margin: 0 0 2px 0 !important;
  padding: 0 !important;
  flex: 0 0 auto !important;
  height: auto !important;
}}

section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {{
  text-decoration: none !important;
  color: #344054 !important;
  font-weight: 500 !important;
  font-size: 14px !important;
  padding: 7px 10px !important;
  border-radius: 8px !important;
  background: transparent !important;
  display: flex !important;
  align-items: center !important;
  gap: 9px !important;
  width: 100% !important;
  min-height: 34px !important;
  max-height: 38px !important;
  line-height: 1.2 !important;
  box-sizing: border-box !important;
  transition: background 0.12s ease, color 0.12s ease !important;
  border: none !important;
}}

section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]
  [data-testid="stMarkdownContainer"] {{
  display: flex !important;
  align-items: center !important;
}}

section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {{
  color: #101828 !important;
  background: #F9FAFB !important;
}}

section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"],
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-selected="true"] {{
  color: #101828 !important;
  font-weight: 600 !important;
  background: #F2F4F7 !important;
}}

section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"],
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] span[translate="no"],
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] svg {{
  color: inherit !important;
  font-size: 18px !important;
  line-height: 1 !important;
  flex-shrink: 0 !important;
  display: inline-flex !important;
  align-items: center !important;
}}

.pd-side-avatar-img {{
  width: 32px;
  height: 32px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}}
.pd-side-avatar-box {{
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #DBEAFE;
  color: #1E40AF;
  font-weight: 700;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid #BFDBFE;
}}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]:has(.pd-side-footer-dock)
  [data-testid="stHorizontalBlock"] {{
  gap: 6px !important;
  margin-top: 2px !important;
  align-items: stretch !important;
}}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]:has(.pd-side-footer-dock)
  [data-testid="stElementContainer"] {{
  position: static !important;
  margin: 0 !important;
}}
section[data-testid="stSidebar"] [data-testid="stButton"] button {{
  font-size: 12px !important;
  font-weight: 600 !important;
  min-height: 32px !important;
  height: 32px !important;
  border-radius: 7px !important;
  box-shadow: none !important;
}}

.pd-page-head {{
  margin: 0 0 10px 0;
  padding: 0 0 10px 0;
  background: transparent;
  border: none;
  border-bottom: 1px solid {LINE};
  border-radius: 0;
  width: 100%;
  max-width: none;
}}
.pd-page-head .eyebrow {{
  margin: 0 0 2px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: {MUTED};
}}
.pd-page-head h1 {{
  margin: 0;
  font-size: 19px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: {INK};
  line-height: 1.25;
}}
.pd-page-head .desc {{
  margin-top: 4px;
  font-size: 13px;
  color: {MUTED};
  max-width: 768px;
  width: 100%;
  line-height: 1.45;
}}
.pd-page-head .pd-page-points {{
  display: none !important;
}}

.pd-case-banner {{
  margin: 0 0 14px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid {LINE};
  background: {SURFACE};
}}
.pd-case-banner .eyebrow {{
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: {MUTED};
  margin-bottom: 4px;
}}
.pd-case-banner .case-id {{
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 12px;
  color: {BRAND};
  font-weight: 600;
}}
.pd-case-banner .subject {{
  font-size: 15px;
  font-weight: 600;
  color: {INK};
  margin: 4px 0 6px;
  line-height: 1.35;
}}
.pd-case-banner .meta {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  font-size: 12px;
  color: {MUTED};
}}
.pd-case-banner.released {{
  border-color: #86EFAC;
  background: #F0FDF4;
}}
.pd-case-banner.released .eyebrow {{
  color: #166534;
}}
.pd-case-banner.empty {{
  border-style: dashed;
  opacity: 0.9;
}}

.pd-empty {{
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 4px;
  padding: 24px 16px;
  margin: 6px 0 12px;
  background: {SURFACE};
  border: 1px dashed {LINE};
  border-radius: 10px;
}}
.pd-empty-title {{
  font-size: 14px;
  font-weight: 600;
  color: {INK};
}}
.pd-empty-hint {{
  font-size: 12px;
  color: {MUTED};
  max-width: 352px;
  line-height: 1.4;
}}

.pd-section {{
  background: {SURFACE};
  border: 1px solid {LINE};
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 12px;
}}
.pd-section-title {{
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: {MUTED};
  margin-bottom: 9px;
}}

.pd-rail-title {{
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: {MUTED};
  margin-bottom: 7px;
}}

/* Mail-style work inbox (email-client list) */
.pd-mail-head {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin: 6px 0 4px 0;
  padding: 0 2px;
}}
.pd-mail-head .title {{
  font-size: 15px;
  font-weight: 600;
  color: {INK};
  letter-spacing: -0.01em;
}}
.pd-mail-head .count {{
  font-size: 12px;
  font-weight: 600;
  color: {MUTED};
  background: #EEF2F6;
  border-radius: 999px;
  padding: 2px 8px;
}}
.pd-mail-row {{
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 2px 1px 6px;
  margin: 0;
  border: none;
  background: transparent;
}}
.pd-mail-dot {{
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-top: 9px;
  flex-shrink: 0;
  background: transparent;
}}
.pd-mail-dot.unread {{ background: {BRAND}; }}
.pd-mail-avatar {{
  width: 34px;
  height: 34px;
  border-radius: 50%;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  margin-top: 1px;
  line-height: 1;
}}
.pd-mail-body {{
  flex: 1;
  min-width: 0;
}}
.pd-mail-top {{
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px 6px;
  margin-bottom: 3px;
}}
.pd-mail-from {{
  font-size: 13px;
  font-weight: 600;
  color: {INK};
  font-family: "IBM Plex Mono", ui-monospace, monospace;
}}
.pd-mail-tag {{
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  padding: 2px 7px;
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
  font-size: 12px;
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
  min-width: 67px;
  padding-top: 2px;
}}
.pd-mail-time {{
  font-size: 11px;
  color: {MUTED};
  white-space: nowrap;
}}
.pd-mail-sla {{
  margin-top: 4px;
  font-size: 10px;
  font-weight: 600;
  color: {BRAND};
  background: #E8F1F8;
  border-radius: 999px;
  padding: 2px 6px;
  display: inline-block;
  max-width: 88px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.pd-mail-sla.overdue {{
  color: #991B1B;
  background: #FEE2E2;
}}
.pd-mail-empty {{
  padding: 18px 10px;
  text-align: center;
  color: {MUTED};
  font-size: 13px;
}}
.pd-mail-hint {{
  display: none !important;
}}
.pd-tour-sample {{
  margin: 10px 0 6px 0;
  padding: 10px 12px;
  border: 1px solid {LINE};
  border-radius: 8px;
  background: {SOFT};
  font-size: 14px;
  line-height: 1.4;
}}
.pd-tour-sample .tag {{
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: {BRAND};
  background: #E8F1FB;
  border-radius: 4px;
  padding: 2px 6px;
  margin-right: 6px;
}}
.pd-tour-sample .subj {{
  margin-top: 6px;
  color: {MUTED};
  font-size: 13px;
}}
.pd-mb-card {{
  border: 1px solid {LINE};
  border-radius: 10px;
  background: {SURFACE};
  padding: 10px 12px;
  margin: 6px 0 9px 0;
}}
.pd-mb-top {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  align-items: baseline;
}}
.pd-mb-top strong {{
  color: {INK};
  font-size: 14px;
}}
.pd-mb-addr {{
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 12px;
  color: {MUTED};
}}
.pd-mb-status {{
  margin-top: 6px;
  font-size: 12px;
  font-weight: 600;
}}
.pd-mb-status.ok {{ color: #166534; }}
.pd-mb-status.warn {{ color: #92400E; }}
.pd-mb-status.bad {{ color: #991B1B; }}
.pd-mb-status.muted {{ color: {MUTED}; }}
.pd-mb-detail {{
  margin-top: 2px;
  font-size: 12px;
  color: {MUTED};
  line-height: 1.35;
}}
/* Dense mail list — hairline rows */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.pd-mail-card-on) {{
  border-color: transparent !important;
  border-left: 3px solid {BRAND} !important;
  box-shadow: none !important;
  background: {SOFT} !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.pd-mail-row) {{
  margin-bottom: 0 !important;
  border: none !important;
  border-bottom: 1px solid {LINE} !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  background: transparent !important;
  padding: 2px 2px !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.pd-mail-row):hover {{
  background: {SOFT} !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.pd-mail-row) div[data-testid="stButton"] > button {{
  min-height: 27px !important;
  height: 27px !important;
  padding: 0 7px !important;
  font-size: 12px !important;
  font-weight: 600 !important;
  border-radius: 6px !important;
  margin-top: 2px !important;
  background: transparent !important;
  border: 1px solid {LINE} !important;
  color: {MUTED} !important;
  box-shadow: none !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.pd-mail-row) div[data-testid="stButton"] > button:hover {{
  background: {SURFACE} !important;
  color: {BRAND} !important;
  border-color: {BRAND} !important;
}}

/* Quieter dataframes */
div[data-testid="stDataFrame"] {{
  border: 1px solid {LINE} !important;
  border-radius: 8px !important;
  overflow: hidden !important;
}}
div[data-testid="stDataFrame"] th {{
  font-size: 12px !important;
  color: {MUTED} !important;
  font-weight: 600 !important;
  background: {SOFT} !important;
}}
div[data-testid="stDataFrame"] td {{
  font-size: 13px !important;
}}

.pd-playbook-rail {{
  margin-top: 14px;
  border: 1px solid {LINE};
  border-radius: 6px;
  background: {SURFACE};
  padding: 11px 12px;
}}
.pd-playbook-rail .hd {{
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: {MUTED};
  margin-bottom: 7px;
}}
.pd-playbook-rail .name {{
  font-size: 15px;
  font-weight: 700;
  color: {BRAND};
  margin-bottom: 3px;
}}
.pd-playbook-rail .meta {{
  font-size: 12px;
  color: {MUTED};
  margin-bottom: 9px;
  line-height: 1.35;
}}
.pd-playbook-rail .step {{
  font-size: 12px;
  color: {INK};
  padding: 4px 0;
  border-top: 1px solid {LINE};
  line-height: 1.35;
}}
.pd-playbook-rail .step .a {{
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: {BRAND};
}}
.pd-playbook-rail .others {{
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px solid {LINE};
}}
.pd-playbook-rail .others .row {{
  font-size: 12px;
  color: {MUTED};
  padding: 3px 0;
}}
.pd-playbook-rail .others .row.on {{
  color: {INK};
  font-weight: 600;
}}

.pd-chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 6px 0 9px 0;
}}
.pd-chip {{
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  border: 1px solid {LINE};
  background: {SOFT};
  color: {INK};
  padding: 3px 7px;
  border-radius: 4px;
}}
.pd-chip.type {{ border-color: {BRAND}; color: {BRAND}; background: #E8F1F8; }}
.pd-chip.review {{
  border-color: {ALERT_BORDER};
  background: {ALERT_BG};
  color: {ALERT_INK};
}}

.pd-type {{
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin: 0 0 2px 0;
}}
.pd-body {{
  font-size: 14px;
  line-height: 1.5;
  color: {INK};
}}

.pd-dl {{
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: 4px 9px;
  font-size: 14px;
  margin-top: 6px;
}}
.pd-dl .k {{ color: {MUTED}; }}
.pd-dl .v {{ color: {INK}; font-weight: 500; }}

.pd-branch {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}}
.pd-node {{
  border: 1px solid {LINE};
  border-radius: 6px;
  padding: 8px 9px;
  background: {BG};
  font-size: 13px;
  color: {MUTED};
}}
.pd-node .nm {{ font-weight: 600; color: {INK}; font-size: 13px; }}
.pd-node .q {{ font-size: 12px; margin-top: 2px; }}
.pd-node.on {{
  border-color: {BRAND};
  background: #E8F1F8;
  color: {INK};
  box-shadow: inset 0 0 0 1px {BRAND};
}}
.pd-node.on .nm {{ color: {BRAND}; font-weight: 700; }}

.pd-callout-row {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}}
.pd-callout {{
  border: 1px solid {LINE};
  border-radius: 6px;
  padding: 11px 13px;
  background: {BG};
}}
.pd-callout .lbl {{
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: {MUTED};
}}
.pd-callout .val {{
  margin-top: 4px;
  font-size: 15px;
  font-weight: 600;
  color: {INK};
}}
.pd-callout .sub {{
  margin-top: 3px;
  font-size: 13px;
  color: {MUTED};
  line-height: 1.4;
}}

.pd-checklist {{
  display: flex;
  flex-wrap: wrap;
  gap: 9px 16px;
  font-size: 13px;
  color: {INK};
  margin-top: 2px;
}}
.pd-checklist .ok {{ color: #1F6B3A; font-weight: 600; }}
.pd-checklist .miss {{ color: {MUTED}; }}

.pd-decision {{
  border: 1px solid {LINE};
  background: #E8F1F8;
  color: {INK};
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 14px;
}}

.pd-compare-col {{
  border: 1px solid {LINE};
  border-radius: 6px;
  background: {SURFACE};
  padding: 12px 14px;
}}
.pd-compare-col .hd {{
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: {MUTED};
  margin-bottom: 6px;
}}
.pd-compare-col .title {{
  font-weight: 700;
  font-size: 15px;
  color: {BRAND};
  margin-bottom: 7px;
}}
.pd-compare-step {{
  font-size: 13px;
  padding: 4px 0;
  border-bottom: 1px solid {LINE};
  color: {INK};
}}
.pd-compare-step .a {{
  font-weight: 700;
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: {BRAND};
}}

.pd-quiet {{
  font-size: 12px;
  color: {MUTED};
  margin-top: 6px;
}}

.pd-outputs {{
  display: grid;
  gap: 2px;
}}
.pd-out-row {{
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid {LINE};
  font-size: 14px;
}}
.pd-out-row:last-child {{ border-bottom: none; }}
.pd-out-row .k {{
  color: {MUTED};
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding-top: 2px;
}}
.pd-out-row .v {{ color: {INK}; line-height: 1.4; word-break: break-word; }}
.pd-out-row .v.flag {{ font-weight: 600; color: {BRAND}; }}
.pd-out-row .v.warn {{ font-weight: 600; color: {ALERT_INK}; }}
.pd-out-row .v.ok {{ font-weight: 600; color: #1F6B3A; }}

/* Draft body — always-visible white box (do not rely on text_area in scroll panes) */
.pd-draft-pre {{
  display: block !important;
  margin: 0 0 10px 0;
  padding: 14px 16px;
  min-height: 120px;
  max-height: 320px;
  overflow-y: auto;
  background: #FFFFFF !important;
  border: 1px solid {LINE};
  border-radius: 8px;
  box-shadow: inset 0 1px 2px rgba(31, 41, 51, 0.04);
  font-family: "IBM Plex Sans", system-ui, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  color: {INK} !important;
  white-space: pre-wrap;
  word-break: break-word;
}}

/* Process desk scroll panes — st.container(height=…) owns overflow; tidy borders */
.stApp:has(.pd-split-desk) section.main [data-testid="stVerticalBlockBorderWrapper"]:has(
  [data-testid="stVerticalBlock"]
) {{
  border: none !important;
}}
/* Height-constrained panes squash text_area to 0 — force readable body/draft boxes */
.stApp:has(.pd-split-desk) [data-testid="stTextArea"] {{
  min-height: 180px !important;
  opacity: 1 !important;
  visibility: visible !important;
}}
.stApp:has(.pd-split-desk) [data-testid="stTextArea"] textarea,
.stApp:has(.pd-split-desk) [data-testid="stTextArea"] [data-baseweb="textarea"],
.stApp:has(.pd-split-desk) [data-testid="stTextArea"] [data-baseweb="base-input"] {{
  min-height: 160px !important;
  height: auto !important;
  opacity: 1 !important;
  color: {INK} !important;
  background: #FFFFFF !important;
}}
@media (max-width: 900px) {{
  /* Stacked on phones — let page scroll; don't trap in short panes */
  .stApp:has(.pd-split-desk) section.main [data-testid="stVerticalBlockBorderWrapper"] {{
    max-height: none !important;
    height: auto !important;
  }}
}}

/* Top toaster stack — notifications / alerts / flags */
.pd-toast-stack {{
  position: sticky;
  top: 6px;
  z-index: 40;
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin: 0 0 14px 0;
}}
.pd-toast {{
  display: grid;
  grid-template-columns: 74px 1fr;
  gap: 10px;
  align-items: start;
  background: {SURFACE};
  border: 1px solid {LINE};
  border-radius: 8px;
  padding: 10px 13px;
  box-shadow: 0 6px 18px rgba(31, 41, 51, 0.08);
  animation: pdToastIn 0.32s ease-out;
}}
.pd-toast .kind {{
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 3px 6px;
  border-radius: 4px;
  text-align: center;
  line-height: 1.2;
}}
.pd-toast .body {{
  font-size: 14px;
  line-height: 1.4;
  color: {INK};
}}
.pd-toast .body strong {{
  display: block;
  font-size: 13px;
  margin-bottom: 2px;
}}
.pd-toast.alert {{ border-left: 4px solid {ALERT_BORDER}; }}
.pd-toast.alert .kind {{ background: {ALERT_BG}; color: {ALERT_INK}; }}
.pd-toast.flag {{ border-left: 4px solid #0F766E; }}
.pd-toast.flag .kind {{ background: #CCFBF1; color: #0F766E; }}
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
  font-weight: 600;
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
  .block-container {{
    padding-left: 12px !important;
    padding-right: 12px !important;
  }}

  /* Slim top bar — hosts Streamlit's open-nav (hamburger) control */
  .stApp:not(:has(.pd-login-anchor)) header[data-testid="stHeader"] {{
    display: block !important;
    visibility: visible !important;
    height: 52px !important;
    min-height: 52px !important;
    background: {BG} !important;
    border-bottom: 1px solid {LINE} !important;
    position: sticky !important;
    top: 0 !important;
    z-index: 1200 !important;
  }}
  .stApp:not(:has(.pd-login-anchor)) header[data-testid="stHeader"] [data-testid="stToolbar"] {{
    display: flex !important;
    visibility: visible !important;
    align-items: center !important;
    height: 52px !important;
    padding: 0 8px !important;
  }}
  /* Keep only the sidebar open control; hide deploy / overflow chrome */
  .stApp:not(:has(.pd-login-anchor)) header[data-testid="stHeader"] [data-testid="stToolbarActions"],
  .stApp:not(:has(.pd-login-anchor)) header[data-testid="stHeader"] [data-testid="stAppDeployButton"],
  .stApp:not(:has(.pd-login-anchor)) header[data-testid="stHeader"] [data-testid="stDecoration"] {{
    display: none !important;
  }}
  .stApp:not(:has(.pd-login-anchor)) header[data-testid="stHeader"] button,
  .stApp:not(:has(.pd-login-anchor)) div[data-testid="stSidebarCollapsedControl"],
  .stApp:not(:has(.pd-login-anchor)) [data-testid="collapsedControl"],
  .stApp:not(:has(.pd-login-anchor)) [data-testid="stExpandSidebarButton"] {{
    display: inline-flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
    width: 40px !important;
    height: 40px !important;
    min-width: 40px !important;
    min-height: 40px !important;
    border-radius: 10px !important;
    background: {SURFACE} !important;
    border: 1px solid {LINE} !important;
    box-shadow: 0 2px 8px rgba(16, 24, 40, 0.08) !important;
    color: {INK} !important;
  }}
  .stApp:not(:has(.pd-login-anchor)) div[data-testid="stSidebarCollapsedControl"] {{
    position: fixed !important;
    top: 8px !important;
    left: 8px !important;
    z-index: 1300 !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
  }}

  /* Overlay drawer when open; allow native collapse when closed */
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] {{
    position: fixed !important;
    z-index: 1250 !important;
    height: 100vh !important;
    max-height: 100vh !important;
    background: #FFFFFF !important;
    border-right: 1px solid #E2E8F0 !important;
    box-shadow: 8px 0 24px rgba(16, 24, 40, 0.14) !important;
  }}
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"][aria-expanded="true"] {{
    display: flex !important;
    visibility: visible !important;
    width: min(300px, 88vw) !important;
    min-width: min(300px, 88vw) !important;
    max-width: min(300px, 88vw) !important;
    left: 0 !important;
    top: 0 !important;
    margin: 0 !important;
    transform: none !important;
  }}
  /* Do not hard-hide collapsed sidebar — Streamlit needs the node for reopen controls */
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"][aria-expanded="false"] {{
    width: 0 !important;
    min-width: 0 !important;
    max-width: 0 !important;
    transform: translateX(-110%) !important;
    visibility: hidden !important;
    pointer-events: none !important;
    box-shadow: none !important;
    border: none !important;
  }}
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"],
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] button[kind="header"],
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {{
    display: flex !important;
    visibility: visible !important;
    width: auto !important;
    height: auto !important;
    opacity: 1 !important;
    pointer-events: auto !important;
  }}
  /* Let nav scroll so Process / Case Log / profile aren't clipped */
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
    overflow-y: auto !important;
    overflow-x: hidden !important;
    -webkit-overflow-scrolling: touch !important;
  }}
  .stApp:not(:has(.pd-login-anchor)) section.main .block-container,
  .stApp:not(:has(.pd-login-anchor)) [data-testid="stMainBlockContainer"] {{
    padding-top: 12px !important;
  }}
  /* Main content must stay usable full-width under the drawer */
  .stApp:not(:has(.pd-login-anchor)) section.main,
  .stApp:not(:has(.pd-login-anchor)) [data-testid="stAppViewContainer"] > .main {{
    width: 100% !important;
    max-width: 100% !important;
    margin-left: 0 !important;
  }}
  /* Stack workbench columns so inbox + case panel both show */
  .stApp:not(:has(.pd-login-anchor)) section.main [data-testid="stHorizontalBlock"] {{
    flex-wrap: wrap !important;
  }}
  .stApp:not(:has(.pd-login-anchor)) section.main [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
    min-width: min(100%, 320px) !important;
    flex: 1 1 100% !important;
  }}
  /* Profile dock stays in-flow on mobile so it doesn't cover the page */
  .stApp:not(:has(.pd-login-anchor)) section[data-testid="stSidebar"]
    [data-testid="stSidebarUserContent"]
    > div
    > div[data-testid="stVerticalBlock"]
    > :last-child {{
    position: static !important;
    width: 100% !important;
    max-width: 100% !important;
    left: auto !important;
    bottom: auto !important;
    margin-top: 16px !important;
    padding-top: 12px !important;
    border-top: 1px solid {LINE} !important;
    background: transparent !important;
  }}
}}
@media (max-width: 640px) {{
  .pd-branch {{ grid-template-columns: 1fr; }}
  .pd-page-head h1 {{ font-size: 19px; }}
  .pd-mail-row {{ grid-template-columns: 1fr; }}
  section.main {{ overflow-x: hidden !important; }}
  .stApp {{ overflow-x: hidden !important; }}
}}
@media (max-width: 320px) {{
  .block-container {{
    padding-left: 8px !important;
    padding-right: 8px !important;
  }}
  .pd-page-head h1 {{ font-size: 18px; }}
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


NAV_LINKS: list[tuple[str, str, str, str]] = [
    # path, label, active_key, material icon
    ("pages/0_Process.py", "Process", "process", ":material/inbox:"),
    ("pages/1_Case_Log.py", "Case Log", "case_log", ":material/receipt_long:"),
    ("pages/2_Playbooks.py", "Playbooks", "playbooks", ":material/account_tree:"),
]

# url_pathname fragment used in page_link href (Streamlit strips "N_" page prefixes)
_NAV_HREF_BY_ACTIVE: dict[str, str] = {
    "process": "Process",
    "case_log": "Case_Log",
    "playbooks": "Playbooks",
}


def _inject_sidebar_visibility() -> None:
    """Keep workbench sidebar usable after login (desktop pinned; mobile collapsible)."""
    st.markdown(
        f"""
<style>
@media (min-width: 901px) {{
  section[data-testid="stSidebar"],
  section[data-testid="stSidebar"][aria-expanded="false"] {{
    display: flex !important;
    visibility: visible !important;
    min-width: 264px !important;
    width: 264px !important;
    max-width: 264px !important;
    height: 100vh !important;
    max-height: 100vh !important;
    overflow: hidden !important;
    background: {SURFACE} !important;
    border-right: 1px solid {LINE} !important;
    transform: none !important;
    margin: 0 !important;
    margin-left: 0 !important;
    left: 0 !important;
    top: 0 !important;
    position: relative !important;
  }}
  div[data-testid="stSidebarCollapsedControl"],
  [data-testid="stSidebarCollapseButton"],
  section[data-testid="stSidebar"] button[kind="header"],
  section[data-testid="stSidebar"] [data-testid="stSidebarHeader"],
  section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"],
  section[data-testid="stSidebar"] [data-testid="collapsedControl"] {{
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
    min-height: 0 !important;
    width: 0 !important;
  }}
}}
@media (max-width: 900px) {{
  header[data-testid="stHeader"] {{
    display: block !important;
    visibility: visible !important;
    height: 52px !important;
    min-height: 52px !important;
    background: {BG} !important;
    border-bottom: 1px solid {LINE} !important;
    z-index: 1200 !important;
  }}
  header[data-testid="stHeader"] button,
  div[data-testid="stSidebarCollapsedControl"],
  [data-testid="stExpandSidebarButton"],
  [data-testid="collapsedControl"] {{
    display: inline-flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
  }}
  section[data-testid="stSidebar"][aria-expanded="true"] {{
    display: flex !important;
    visibility: visible !important;
    position: fixed !important;
    z-index: 1250 !important;
    left: 0 !important;
    top: 0 !important;
    width: min(300px, 88vw) !important;
    min-width: min(300px, 88vw) !important;
    max-width: min(300px, 88vw) !important;
    height: 100vh !important;
    background: {SURFACE} !important;
    border-right: 1px solid {LINE} !important;
    transform: none !important;
    margin: 0 !important;
  }}
  section[data-testid="stSidebar"][aria-expanded="false"] {{
    width: 0 !important;
    min-width: 0 !important;
    max-width: 0 !important;
    transform: translateX(-110%) !important;
    visibility: hidden !important;
    pointer-events: none !important;
    box-shadow: none !important;
  }}
  section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"],
  section[data-testid="stSidebar"] button[kind="header"] {{
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
  }}
  section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
  section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
    overflow-y: auto !important;
    overflow-x: hidden !important;
  }}
}}
section[data-testid="stSidebar"] *,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
  scrollbar-width: none !important;
}}
section[data-testid="stSidebar"]::-webkit-scrollbar,
section[data-testid="stSidebar"] *::-webkit-scrollbar {{
  width: 0 !important;
  height: 0 !important;
  display: none !important;
}}
</style>
        """,
        unsafe_allow_html=True,
    )


def chrome(active: str = "process") -> bool:
    """Single-column side nav. Returns False while login is showing."""
    user = current_user()
    if not user:
        require_login()
        return False

    prepare_tour_workspace()
    _inject_sidebar_visibility()

    role = str(user.get("role") or "agent")
    role_title = ROLE_PROFILES.get(role, {}).get("title") or role.title()
    email = str(
        user.get("email")
        or (USERS.get(str(user.get("username") or "")) or {}).get("email")
        or f"{user.get('username') or 'user'}@pulsedesk.demo"
    )
    active_href = _NAV_HREF_BY_ACTIVE.get(active, "Process")
    brand_sub = (
        "Lead escalation desk" if role == "lead" else "Agent workbench"
    )
    env_kind = "demo"
    env_label = "Demo"
    try:
        from integrations.gmail_inbox import list_mailboxes

        n_mail = len(list_mailboxes())
        if n_mail:
            env_kind = "connected"
            env_label = f"Connected · {n_mail}"
    except Exception:  # noqa: BLE001
        pass

    # Outside sidebar so the <style> block does not create an extra nav node
    st.markdown(
        f"""
<style>
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][href*="{active_href}"] {{
  color: #101828 !important;
  font-weight: 600 !important;
  background: #F2F4F7 !important;
}}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][href*="{active_href}"]:hover {{
  background: #EAECF0 !important;
  color: #101828 !important;
}}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][href*="{active_href}"]
  [data-testid="stMarkdownContainer"],
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][href*="{active_href}"]
  [data-testid="stMarkdownContainer"] * {{
  color: #101828 !important;
  font-weight: 600 !important;
}}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][href*="{active_href}"]
  [data-testid="stIconMaterial"],
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][href*="{active_href}"]
  span[translate="no"],
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][href*="{active_href}"] svg {{
  color: #344054 !important;
}}
</style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        initials = _esc_html(str(user.get("initials") or "PD"))
        avatar_html = f'<div class="pd-side-avatar-box">{initials}</div>'

        st.markdown(
            f"""
<div class="pd-side-brand-card">
  <div class="pd-side-logo-mark" aria-hidden="true">PD</div>
  <div class="pd-side-brand-meta">
    <div class="title-row">
      <span class="brand-title">PulseDesk</span>
      <span class="badge-env {env_kind}">{_esc_html(env_label)}</span>
    </div>
    <div class="brand-sub">{_esc_html(brand_sub)}</div>
  </div>
</div>
<div class="pd-side-nav-label">WORKBENCH</div>
            """,
            unsafe_allow_html=True,
        )

        for path_name, label, _key, icon in NAV_LINKS:
            st.page_link(path_name, label=label, icon=icon)

        with st.container():
            st.markdown(
                f"""
<div class="pd-side-footer-dock">
  <div class="pd-side-user-card">
    {avatar_html}
    <div class="user-info">
      <div class="user-name">{_esc_html(user.get("name") or "")}</div>
      <div class="user-role">{_esc_html(role_title)} · {_esc_html(email)}</div>
    </div>
  </div>
</div>
                """,
                unsafe_allow_html=True,
            )
            tour_col, out_col = st.columns(2, gap="small")
            with tour_col:
                if st.button("Take tour", width="stretch", key="take_tour"):
                    start_guided_tour(switch_to_process=True)
            with out_col:
                if st.button("Sign out", type="primary", width="stretch", key="sign_out"):
                    logout()

    render_guided_tour_if_needed()
    return True



def page_header(
    title: str,
    desc: str = "",
    *,
    eyebrow: str = "",
    points: list[str] | None = None,
) -> None:
    """Page title block with short overview and optional bullet points."""
    eye = (
        f'<p class="eyebrow">{_esc_html(eyebrow)}</p>'
        if eyebrow
        else '<p class="eyebrow">PulseDesk</p>'
    )
    desc_html = f'<div class="desc">{_esc_html(desc)}</div>' if desc else ""
    points_html = ""
    if points:
        items = "".join(f"<li>{_esc_html(p)}</li>" for p in points if p)
        if items:
            points_html = f'<ul class="pd-page-points">{items}</ul>'
    st.markdown(
        f'<div class="pd-page-head">{eye}<h1>{_esc_html(title)}</h1>'
        f"{desc_html}{points_html}</div>",
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
    <div class="hd" style="margin-bottom:4px;">All six paths</div>
    {"".join(others)}
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def branch_label(key: str) -> str:
    return BRANCH_LABELS.get(key, key)


def branch_short(key: str) -> str:
    """Compact queue label for inbox tags (avoids wrapping)."""
    pb = PLAYBOOK_BY_KEY.get(key)
    if pb:
        return pb[2]
    return branch_label(key)


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
        if t == "case_reopened":
            # Prior release no longer locks the gate
            agent_decision = None
            if lead_decision == "approved_release":
                lead_decision = None
            continue
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
    # Fallback: outputs pack, then draft_response action payload
    if not (draft or "").strip():
        for a in db.get_case_actions(case_id):
            at = a.get("action_type")
            payload = _json_obj(a.get("payload_json"))
            if at == "emit_case_outputs":
                cand = str(
                    payload.get("draft_response")
                    or payload.get("email_draft")
                    or ""
                ).strip()
            elif at == "draft_response":
                cand = str(
                    payload.get("email_draft")
                    or payload.get("draft_response")
                    or payload.get("body")
                    or ""
                ).strip()
            else:
                continue
            if cand and cand != "Customer confirmation / acknowledgement draft generated.":
                draft = cand
                break

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
    status = case.get("status") or db.STATUS_OPEN
    # Released / closed cases must never re-open the review gate from a stale flag
    if status == db.STATUS_RELEASED:
        needs_review = False
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
        "replay": status == db.STATUS_RELEASED,
        "agent_decision": agent_decision,
        "lead_decision": lead_decision,
        "status": status,
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
    case_row = db.get_case(case_id) or {}

    send_meta: dict[str, Any] | None = None
    if decision in ("approved_send", "edited_send"):
        from integrations.gmail_inbox import try_send_case_release

        send_meta = try_send_case_release(case_row, draft)
        if send_meta.get("ok") and not send_meta.get("simulated"):
            release_detail = (
                f"{actor} released draft — email sent "
                f"({send_meta.get('from')} → {send_meta.get('to')})."
            )
        else:
            release_detail = (
                f"{actor} released draft — "
                f"{send_meta.get('detail') or 'simulated (no live send)'}."
            )
        labels = {
            "approved_send": ("agent_approved_send", release_detail),
            "edited_send": ("agent_edited_send", release_detail),
            "escalated_lead": (
                "agent_escalated_to_lead",
                f"{actor} escalated to Tech Lead — reason: {reason or 'n/a'}.",
            ),
        }
    else:
        labels = {
            "approved_send": (
                "agent_approved_send",
                f"{actor} released outbound draft (simulated).",
            ),
            "edited_send": (
                "agent_edited_send",
                f"{actor} released edited draft (simulated).",
            ),
            "escalated_lead": (
                "agent_escalated_to_lead",
                f"{actor} escalated to Tech Lead — reason: {reason or 'n/a'}.",
            ),
        }

    action_type, detail = labels[decision]
    order = db.next_action_order(case_id)
    payload: dict[str, Any] = {
        "decision": decision,
        "draft_chars": len(draft or ""),
        "reason": reason,
        "by": actor,
    }
    if send_meta:
        payload["outbound"] = send_meta
    db.log_action(case_id, order, action_type, detail, payload)

    if decision in ("approved_send", "edited_send"):
        db.log_message(case_id, draft or "", direction="outbound", channel="email")
        db.set_needs_review(case_id, False)
        db.set_case_status(case_id, db.STATUS_RELEASED, updated_by=actor)
        result["needs_review"] = False
        result["status"] = db.STATUS_RELEASED
        result["outbound_send"] = send_meta
        # Leave the active desk — reopen later via Case Log → Replay
        st.session_state.selected_inbox_id = None
        st.session_state["_suppress_inbox_autofocus"] = True
        st.session_state["_release_flash"] = {
            "case_id": case_id,
            "sent": bool(send_meta and send_meta.get("ok") and not send_meta.get("simulated")),
            "detail": (send_meta or {}).get("detail") or "Case marked Closed.",
            "show_empty": True,
        }
        st.session_state["_pending_workspace"] = {
            "subject": "",
            "body": "",
            "source_id": "",
            "selected_inbox_id": None,
            "last_result": None,
        }
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
            "payload": payload,
        }
    )
    rem["steps"] = steps
    if decision == "edited_send":
        rem["email_draft"] = draft
    if decision in ("approved_send", "edited_send"):
        rem["steps"].append(
            {
                "action_type": "set_resolved_status",
                "detail": "Status → Closed",
                "payload": {
                    "status": db.STATUS_RELEASED,
                    "resolved_status_log": True,
                    "outbound": send_meta,
                },
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
    _toast_decision(decision, case_id, send_meta=send_meta)

    # Re-hydrate from SQLite so the spine matches DB (status / decision / gate)
    if decision in ("approved_send", "edited_send", "escalated_lead"):
        rebuilt = rebuild_result_from_case(case_id)
        if rebuilt:
            rebuilt["replay"] = False
            if send_meta:
                rebuilt["outbound_send"] = send_meta
            rebuilt["agent_decision"] = decision
            if decision in ("approved_send", "edited_send"):
                rebuilt["needs_review"] = False
                rebuilt["status"] = db.STATUS_RELEASED
                rebuilt["replay"] = False
            return rebuilt
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
    case_row = db.get_case(case_id) or {}

    send_meta: dict[str, Any] | None = None
    if decision == "approved_release":
        from integrations.gmail_inbox import try_send_case_release

        body_draft = draft or (result.get("remediation") or {}).get("email_draft") or ""
        send_meta = try_send_case_release(case_row, body_draft)
        if send_meta.get("ok") and not send_meta.get("simulated"):
            approve_detail = (
                f"{actor} approved release — email sent "
                f"({send_meta.get('from')} → {send_meta.get('to')})."
            )
        else:
            approve_detail = (
                f"{actor} approved release — "
                f"{send_meta.get('detail') or 'simulated (no live send)'}."
            )
    else:
        approve_detail = f"{actor} approved release (simulated)."

    labels = {
        "acknowledged": (
            "lead_acknowledged",
            f"{actor} acknowledged escalation — ownership taken.",
        ),
        "approved_release": ("lead_approved_release", approve_detail),
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
    if decision == "approved_release" and draft:
        payload["draft_chars"] = len(draft)
        payload["draft_edited"] = True
    if send_meta:
        payload["outbound"] = send_meta
    order = db.next_action_order(case_id)
    db.log_action(case_id, order, action_type, detail, payload)

    if decision == "approved_release":
        body = draft or (result.get("remediation") or {}).get("email_draft") or ""
        db.log_message(case_id, body, direction="outbound", channel="email")
        db.set_needs_review(case_id, False)
        db.set_case_status(case_id, db.STATUS_RELEASED, updated_by=actor)
        result["needs_review"] = False
        result["status"] = db.STATUS_RELEASED
        result["outbound_send"] = send_meta
        st.session_state.lead_queue_focus = None
        st.session_state.selected_inbox_id = None
        st.session_state["_suppress_inbox_autofocus"] = True
        st.session_state["_release_flash"] = {
            "case_id": case_id,
            "sent": bool(send_meta and send_meta.get("ok") and not send_meta.get("simulated")),
            "detail": (send_meta or {}).get("detail") or "Case marked Closed.",
            "show_empty": True,
        }
        st.session_state["_pending_workspace"] = {
            "subject": "",
            "body": "",
            "source_id": "",
            "selected_inbox_id": None,
            "last_result": None,
        }
        if draft:
            rem = dict(result.get("remediation") or {})
            rem["email_draft"] = draft
            result["remediation"] = rem
            result["draft_saved_text"] = draft
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
                "detail": "Status → Closed (lead)",
                "payload": {
                    "status": db.STATUS_RELEASED,
                    "resolved_status_log": True,
                    "outbound": send_meta,
                },
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
    _toast_decision(decision, case_id, send_meta=send_meta)
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
    raw = (name or "").strip()
    if not raw:
        return "?"
    # Account IDs → fixed "AC" so avatars stay consistent
    if raw.upper().startswith("ACC"):
        return "AC"
    parts = [p for p in raw.replace("_", " ").replace(".", " ").replace("-", " ").split() if p]
    if not parts:
        return raw[:2].upper()
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
    branch = branch_short(str(case.get("request_type") or ""))
    when = _mail_when(case.get("received_at") or case.get("created_at"))
    sla = db.sla_remaining(case.get("sla_due_at"))
    mailbox = (case.get("source_mailbox") or "").strip()
    unread = status in (db.STATUS_OPEN, db.STATUS_RETURNED) and not (
        case.get("assigned_to") or ""
    ).strip()
    sla_cls = "pd-mail-sla overdue" if "OVERDUE" in sla else "pd-mail-sla"
    sla_block = (
        f'<div class="{sla_cls}">{_esc_html(sla)}</div>' if sla and sla != "—" else ""
    )
    mailbox_tag = (
        f'<span class="pd-mail-tag branch">{_esc_html(mailbox)}</span>' if mailbox else ""
    )
    marker = '<div class="pd-mail-card-on"></div>' if active else ""
    open_pill = (
        '<span class="pd-mail-open-pill">Open</span>' if active else ""
    )
    unread_cls = " unread" if unread else ""
    avatar = _mail_initials(from_label)
    color = _mail_avatar_color(from_label)
    # Single continuous HTML string — blank lines make Streamlit print raw tags
    return (
        f"{marker}"
        f'<div class="pd-mail-row">'
        f'<span class="pd-mail-dot{unread_cls}"></span>'
        f'<span class="pd-mail-avatar" style="background:{color}">{_esc_html(avatar)}</span>'
        f'<div class="pd-mail-body">'
        f'<div class="pd-mail-top">'
        f'<span class="pd-mail-from">{_esc_html(from_label)}</span>'
        f"{open_pill}"
        f'<span class="pd-mail-tag st-{_esc_html(status)}">{_esc_html(status_label)}</span>'
        f'<span class="pd-mail-tag branch">{_esc_html(branch)}</span>'
        f"{mailbox_tag}"
        f"</div>"
        f'<div class="pd-mail-subline">'
        f"<strong>{_esc_html(subject)}</strong>"
        f" — {_esc_html(preview)}"
        f"</div></div>"
        f'<div class="pd-mail-aside">'
        f'<div class="pd-mail-time">{_esc_html(when)}</div>'
        f"{sla_block}"
        f"</div></div>"
    )


def render_mail_case_list(
    cases: list[dict[str, Any]],
    *,
    selected_id: str | None,
    key_prefix: str,
    title: str = "Inbox",
    allow_claim: bool = False,
    claim_username: str = "",
    assignment_view: str = "All",
) -> dict[str, str | None]:
    """Mail-style inbox. Returns {{open, claim, unassign}} case ids when clicked.

    Claim = take ownership (moves case into Mine). On Mine, only Unassign is offered.
    """
    _render_html(
        f'<div class="pd-mail-head">'
        f'<span class="title">{_esc_html(title)}</span>'
        f'<span class="count">{len(cases)}</span></div>'
    )
    result: dict[str, str | None] = {"open": None, "claim": None, "unassign": None}
    if not cases:
        _render_html(
            '<div class="pd-empty">'
            '<div class="pd-empty-title">No cases in this view</div>'
            '<div class="pd-empty-hint">Try another filter, sync Gmail, or compose a new request.</div>'
            "</div>"
        )
        return result

    me = (claim_username or "").strip()
    for case in cases:
        cid = str(case.get("case_id") or "")
        active = bool(selected_id and cid == selected_id)
        # Prefer live DB assignee so Claim flips to Unassign right after claim
        live = db.get_case(cid) if (active or allow_claim) and cid else None
        assignee = str(
            (live or case).get("assigned_to") or case.get("assigned_to") or ""
        ).strip()
        is_mine = bool(me and assignee == me) or assignment_view == "Mine"
        with st.container(border=True):
            _render_html(mail_case_row_html(case, active=active))
            # Always offer Open/Reload so Mine cards are never dead-ends
            open_label = "Reload workbench" if active else "Open"
            if st.button(
                open_label,
                key=f"{key_prefix}_open_{cid}",
                width="stretch",
                type="primary" if not active else "secondary",
                help="Load this case into the right-hand workbench.",
            ):
                result["open"] = cid

            if allow_claim:
                if is_mine:
                    if active:
                        st.caption("Assigned to you · open in workbench")
                    if st.button(
                        "Unassign",
                        key=f"{key_prefix}_unassign_{cid}",
                        width="stretch",
                        help="Return this case to Unassigned.",
                    ):
                        result["unassign"] = cid
                elif not assignee:
                    if st.button(
                        "Claim",
                        key=f"{key_prefix}_claim_{cid}",
                        width="stretch",
                        help="Assign this case to you (appears under Mine).",
                    ):
                        result["claim"] = cid
                else:
                    st.caption(f"Assigned to `{assignee}`")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(
                            "Claim for me",
                            key=f"{key_prefix}_claim_{cid}",
                            width="stretch",
                            help="Take ownership from the current assignee.",
                        ):
                            result["claim"] = cid
                    with c2:
                        if st.button(
                            "Unassign",
                            key=f"{key_prefix}_unassign_{cid}",
                            width="stretch",
                        ):
                            result["unassign"] = cid
            elif active:
                st.caption("Open in workbench")
    return result


def filter_cases_by_query(
    cases: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    if not q:
        return cases
    tokens = [t for t in q.replace(",", " ").split() if t]
    if not tokens:
        return cases
    out: list[dict[str, Any]] = []
    for c in cases:
        req = str(c.get("request_type") or "")
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
                "source_mailbox",
                "urgency",
            )
        ).lower()
        blob = f"{blob} {branch_label(req).lower()}"
        if all(tok in blob for tok in tokens):
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
    # Drop stale draft widget keys so §5 remounts with the rebuilt email body
    clear_draft_keys()
    # Non-widget keys can be set anytime
    st.session_state["workspace_source_id"] = case_id
    st.session_state["selected_inbox_id"] = case_id
    st.session_state["last_result"] = rebuilt
    # Subject/Body are widgets — queue for Process to apply before they instantiate
    st.session_state["_pending_workspace"] = {
        "subject": str(case.get("subject") or ""),
        "body": str(case.get("body") or ""),
        "source_id": case_id,
        "selected_inbox_id": case_id,
        "last_result": rebuilt,
    }
    return True


def workspace_needs_case_reload(case_id: str | None) -> bool:
    """True when the workbench should (re)hydrate this case from SQLite."""
    cid = str(case_id or "").strip()
    if not cid:
        return False
    if str(st.session_state.get("workspace_source_id") or "") != cid:
        return True
    result = st.session_state.get("last_result")
    if not isinstance(result, dict) or str(result.get("case_id") or "") != cid:
        return True
    subj = str(st.session_state.get("workspace_subject") or "").strip()
    body = str(st.session_state.get("workspace_body") or "").strip()
    if subj or body:
        return False
    case = db.get_case(cid) or {}
    return bool(str(case.get("subject") or "").strip() or str(case.get("body") or "").strip())


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
    return html.escape(str(value if value not in (None, "") else "—"), quote=True)


def _render_html(fragment: str) -> None:
    """Render HTML safely — Streamlit Markdown breaks multi-line HTML on blank lines."""
    compact = " ".join(line.strip() for line in fragment.splitlines() if line.strip())
    if hasattr(st, "html"):
        st.html(compact)
    else:
        st.markdown(compact, unsafe_allow_html=True)


def _toast_decision(
    kind: str, case_id: str, *, send_meta: dict[str, Any] | None = None
) -> None:
    sent = bool(send_meta and send_meta.get("ok") and not send_meta.get("simulated"))
    if kind in ("approved_send", "edited_send", "approved_release"):
        if sent:
            label = "Closed · email sent"
        elif send_meta:
            label = "Closed · simulated send"
        else:
            label = "Closed"
    else:
        labels = {
            "escalated_lead": "Escalated to lead",
            "acknowledged": "Lead acknowledged",
            "returned_to_agent": "Returned to agent",
            "note": "Lead note saved",
        }
        label = labels.get(kind, kind)
    st.toast(f"{label} · {case_id}")


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
    live: dict[str, Any] = {}
    # Prefer live DB truth — session result can lag right after Release
    if case_id:
        live = db.get_case(case_id) or {}
        live_status = str(live.get("status") or "")
        if live_status == db.STATUS_RELEASED:
            needs_review = False
            case_status_live = db.STATUS_RELEASED
        else:
            case_status_live = live_status or None
        agent_live, lead_live = _decision_from_actions(case_id)
        if agent_live:
            decision = agent_live
        if lead_live:
            lead_decision = lead_live
        if live and "needs_review" in live and live_status != db.STATUS_RELEASED:
            needs_review = bool(live.get("needs_review"))
    else:
        case_status_live = None
    role = active_role()
    is_agent = role == "agent"
    is_lead = role == "lead"
    case_status = case_status_live or result.get("status") or (
        db.STATUS_ON_HOLD if needs_review else db.STATUS_OPEN
    )
    # Stale release decisions must not lock the gate after Case Log reopen
    if decision in ("approved_send", "edited_send") and case_status != db.STATUS_RELEASED:
        decision = None
    if lead_decision == "approved_release" and case_status != db.STATUS_RELEASED:
        lead_decision = None
    # Audit-only lock: closed cases (Case Log replay of a Closed case)
    is_replay = bool(result.get("replay")) and case_status == db.STATUS_RELEASED
    open_escalation = case_is_open_escalation(
        {
            **result,
            "agent_decision": decision,
            "lead_decision": lead_decision,
            "status": case_status,
            "needs_review": needs_review,
        }
    )
    # Closed cases never show the release / escalate gate
    if case_status == db.STATUS_RELEASED:
        needs_review = False
    status_label = db.STATUS_LABELS.get(case_status, case_status)
    status_by = result.get("status_updated_by") or live.get("status_updated_by") or "—"
    status_at = (
        (result.get("status_updated_at") or live.get("status_updated_at") or "")
        [:19]
        .replace("T", " ")
    )
    lead_note = (result.get("lead_note_to_agent") or "").strip()
    return_reason = (result.get("return_reason") or "").strip()
    escalate_reason = (result.get("escalate_reason") or "").strip()

    if lead_note or return_reason:
        st.warning(
            f"**Lead returned this case**"
            + (f" — {return_reason}" if return_reason else "")
            + (f"\n\nNote for agent: {lead_note}" if lead_note else "")
        )

    flash = st.session_state.pop("_release_flash", None)
    if isinstance(flash, dict) and flash.get("case_id") == case_id:
        if flash.get("sent"):
            st.success(
                f"**Case closed** — email sent. {flash.get('detail') or ''}"
            )
        else:
            st.success(
                f"**Case closed** — {flash.get('detail') or 'Logged as closed.'}"
            )
    elif case_status == db.STATUS_RELEASED:
        outbound = result.get("outbound_send") or {}
        if outbound.get("ok") and not outbound.get("simulated"):
            st.success(
                f"**Case closed** — reply emailed "
                f"({outbound.get('from')} → {outbound.get('to')})."
            )
        else:
            st.success(
                "**Case closed** — removed from active Mine / Unassigned. "
                "Reopen later from Case Log → Replay on Process."
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
  <div style="font-size:13px;color:{MUTED};">
    Case <span class="pd-mono">{case_id}</span>
  </div>
  <div class="pd-body" style="margin-top:9px;"><strong>Why this branch:</strong> {_esc_html(why_line.replace('**',''))}</div>
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
        f'<div class="pd-section-title" style="margin-top:12px;">Entities</div>'
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

    # 5) Draft — recover body from rem / outputs / action payloads
    draft = (
        (rem.get("email_draft") or "").strip()
        or str((result.get("outputs") or {}).get("draft_response") or "").strip()
        or str(result.get("draft_saved_text") or "").strip()
    )
    if not draft:
        for step in steps:
            if (step.get("action_type") or "") != "draft_response":
                continue
            payload = _payload_dict(step)
            cand = str(
                payload.get("email_draft")
                or payload.get("draft_response")
                or payload.get("body")
                or ""
            ).strip()
            if cand:
                draft = cand
                break
    if draft and not (rem.get("email_draft") or "").strip():
        rem = dict(rem)
        rem["email_draft"] = draft
        result["remediation"] = rem
    baseline_key = f"draft_baseline_{case_id}"
    edit_key = f"draft_edit_mode_{case_id}"
    if baseline_key not in st.session_state or (
        draft and not str(st.session_state.get(baseline_key) or "").strip()
    ):
        st.session_state[baseline_key] = draft
    if edit_key not in st.session_state:
        st.session_state[edit_key] = False

    editing = bool(st.session_state.get(edit_key)) and not decision
    agent_can_decide = (
        is_agent
        and not is_replay
        and not decision
        and case_status
        in (db.STATUS_ON_HOLD, db.STATUS_RETURNED, db.STATUS_OPEN)
    )
    lead_editing = bool(is_lead and open_escalation)
    use_edit_buf = (editing and agent_can_decide) or lead_editing

    st.markdown(
        '<div class="pd-section"><div class="pd-section-title">5 · Draft customer response</div></div>',
        unsafe_allow_html=True,
    )

    draft_now = draft
    if use_edit_buf:
        # Form + value= always shows the body (no sticky empty widget keys)
        with st.form(f"draft_edit_form_{case_id}", clear_on_submit=False):
            edited = st.text_area(
                "Edit draft",
                value=draft or "",
                height=220,
                label_visibility="collapsed",
            )
            apply_edits = st.form_submit_button(
                "Apply edits",
                type="primary",
                width="stretch",
            )
        if apply_edits:
            draft_now = (edited or "").strip() or draft
            if is_lead and open_escalation:
                rem = dict(result.get("remediation") or {})
                rem["email_draft"] = draft_now
                result["remediation"] = rem
                result["draft_saved_text"] = draft_now
                st.session_state.last_result = result
            else:
                st.session_state.last_result = save_agent_draft(result, draft_now)
            st.session_state[edit_key] = False
            st.session_state[baseline_key] = draft_now
            st.rerun()
        else:
            draft_now = draft
    elif draft:
        # Real Streamlit white text box (no key → value= always paints; safe outside height pane)
        st.text_area(
            "Draft",
            value=draft,
            height=220,
            disabled=True,
            label_visibility="collapsed",
        )
    else:
        st.warning(
            "No draft body found for this case. Re-run the playbook, or open from "
            "**Case Log → Replay** after a fresh run."
        )

    if is_lead and open_escalation:
        st.caption(
            "Change the draft above, click **Apply edits**, then **Approve release** "
            "or **Return to agent**."
        )
    elif agent_can_decide and needs_review:
        if editing:
            st.caption(
                "Edit the text, click **Apply edits**, then **Release** or **Escalate**."
            )
        else:
            st.caption(
                "On hold — draft shown above. **Edit** → **Apply edits**, then **Release** "
                "or **Escalate to lead**."
            )
    elif agent_can_decide:
        st.caption(
            f"Confidence ≥ {CONFIDENCE_REVIEW_THRESHOLD:.0%} — playbook + draft ready. "
            "**Release draft** closes the case (and emails the customer if Gmail is connected). "
            "Click **Edit** only if you need to change the wording."
        )

    # Agent must always finish: Release (close) or Escalate — high or low confidence
    can_agent_act = agent_can_decide
    if can_agent_act:
        # Prefer latest saved / rem draft (Apply edits updates last_result)
        draft_now = (
            str(result.get("draft_saved_text") or "").strip()
            or (rem.get("email_draft") or "").strip()
            or draft
        )
        baseline = st.session_state.get(baseline_key) or draft
        dirty = (draft_now or "").strip() != (baseline or "").strip()
        saved_text = result.get("draft_saved_text")
        unsaved = bool(editing)  # still in editor — must Apply first for Save path

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
                help="Marks case Closed. Sends real email if a Gmail mailbox is connected.",
                disabled=editing,
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
            save = st.button(
                "Save",
                key=f"dec_save_{case_id}",
                width="stretch",
                disabled=True,
                help="Use Apply edits inside the editor, then Release.",
            )
        with g4:
            escalate = st.button(
                "Escalate to lead",
                key=f"dec_esc_{case_id}",
                width="stretch",
                help="Requires a reason code.",
                disabled=editing,
            )

        flash_key = f"draft_save_flash_{case_id}"
        if edit:
            st.session_state[edit_key] = True
            st.session_state.pop(flash_key, None)
            st.rerun()
        if send and not editing:
            kind = "edited_send" if dirty else "approved_send"
            st.session_state[edit_key] = False
            st.session_state.pop(flash_key, None)
            st.session_state.last_result = apply_agent_decision(
                result, kind, draft_now
            )
            st.rerun()
        if escalate and not editing:
            if not esc_reason:
                st.error("Pick an escalate reason.")
            else:
                st.session_state[edit_key] = False
                st.session_state.pop(flash_key, None)
                st.session_state.last_result = apply_agent_decision(
                    result, "escalated_lead", draft_now, reason=esc_reason
                )
                st.rerun()

        if editing:
            st.info("Edit the draft above, then **Apply edits**. After that you can Release.")
        if st.session_state.pop(flash_key, False):
            st.success("Draft saved — still open. Release to close or Escalate when ready.")

    elif is_lead and open_escalation and case_id:
        st.markdown(
            '<div class="pd-section"><div class="pd-section-title">Lead actions</div></div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Approve release sends the draft when a Gmail mailbox is connected; "
            "otherwise it logs a simulated release."
        )
        draft_now = (
            str(result.get("draft_saved_text") or "").strip()
            or (rem.get("email_draft") or "").strip()
            or draft
        )
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
            if not (note_txt or "").strip():
                st.error("Add a short note before saving.")
            else:
                st.session_state.last_result = apply_lead_decision(
                    result, "note", note=note_txt.strip()
                )
                st.rerun()

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
