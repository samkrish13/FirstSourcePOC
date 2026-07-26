"""Playbooks — 6-row remediation table for interview clarity."""

from __future__ import annotations

import streamlit as st

from ui.shell import (
    CONFIDENCE_REVIEW_THRESHOLD,
    PLAYBOOKS,
    chrome,
    page_header,
    page_setup,
)

page_setup("Playbooks")
if not chrome("playbooks"):
    st.stop()
page_header(
    "Playbooks",
    "Six remediation branches — queue, steps, and expected outputs for each path.",
    eyebrow="Remediation map",
)

st.markdown(
    '<div class="pd-section"><div class="pd-section-title">Branch catalog</div></div>',
    unsafe_allow_html=True,
)
st.dataframe(
    [
        {
            "Category": name,
            "Queue": queue,
            "Downstream steps": summary,
            "Expected outputs": {
                "billing_dispute": "Ack draft · Billing route · 48h follow-up · status log",
                "service_outage": "Status draft · Network route · SLA flag · status log",
                "complaint_escalation": "Recovery draft · supervisor alert · callback · escalated log",
                "sim_port": "Activation draft · Port/SIM route · 24h follow-up · status log",
                "plan_change": "Confirmation draft · Care route · order follow-up · status log",
                "general_enquiry": "FAQ draft · General route · resolved/open log",
            }.get(key, "Draft · route · follow-up · log"),
            "Key": key,
        }
        for key, name, queue, summary in PLAYBOOKS
    ],
    width="stretch",
    hide_index=True,
)

st.markdown(
    f"""
<div class="pd-section">
  <div class="pd-section-title">Mandatory outcomes (every branch)</div>
  <ol style="margin:0;padding-left:18px;font-size:14px;line-height:1.55;color:#1F2933;">
    <li><strong>Classification + urgency</strong></li>
    <li><strong>Branch-specific action summary</strong></li>
    <li><strong>Draft / confirmation message</strong></li>
    <li><strong>Routing notification</strong> (+ supervisor alert on escalation)</li>
    <li><strong>Follow-up / SLA flag</strong> when applicable</li>
    <li><strong>Human-in-the-loop flag</strong> when confidence &lt; {CONFIDENCE_REVIEW_THRESHOLD:.0%}</li>
    <li><strong>Resolved status log</strong> + Case Log persistence</li>
  </ol>
  <p style="margin:12px 0 0;font-size:14px;color:#5B6570;">
    Confidence gate: below {CONFIDENCE_REVIEW_THRESHOLD:.0%} → Needs Review + pause auto-send.
  </p>
</div>
    """,
    unsafe_allow_html=True,
)
