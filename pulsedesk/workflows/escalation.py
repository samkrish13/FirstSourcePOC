"""Complaint / escalation remediation branch."""

from __future__ import annotations

import re
from typing import Any

from workflows import actions
from workflows.llm import draft_response


def _extract_prior_tickets(text: str) -> list[str]:
    return re.findall(r"#?T-\d+", text, flags=re.I)


def run(classification: dict[str, Any], subject: str, body: str) -> dict[str, Any]:
    entities = classification.get("entities") or {}
    account = entities.get("account") or "UNKNOWN"
    sentiment = classification.get("sentiment", "negative")
    prior = _extract_prior_tickets(f"{subject}\n{body}")

    steps: list[dict[str, Any]] = []

    # 1) P1 Retention case
    ticket = actions.create_ticket(
        queue="Retention",
        priority="P1",
        summary=f"Escalation / retention risk for {account}",
        sentiment=sentiment,
        prior_tickets=prior,
        recovery_offer_queued=True,
    )
    steps.append(ticket)
    ticket_id = ticket["payload"]["ticket_id"]

    # 2) Supervisor alert (Slack + email simulation)
    prior_note = f" Prior tickets: {', '.join(prior)}." if prior else ""
    notify_msg = (
        f"P1 escalation on {account}. Sentiment={sentiment}. "
        f"Case {ticket_id}.{prior_note} Same-day callback required."
    )
    steps.append(actions.notify_lead("slack", notify_msg))
    steps.append(
        actions.supervisor_alert(
            notify_msg,
            channels="slack+email",
        )
    )

    # 3) Route + same-day callback follow-up
    steps.append(
        actions.route_to_team(
            "Retention / Team Lead",
            "Dissatisfied customer escalation — senior ownership required",
        )
    )
    steps.append(
        actions.set_callback(
            same_day=True,
            note=f"Same-day Team Lead callback for {ticket_id}",
        )
    )
    steps.append(
        actions.set_resolved_status(
            "open_escalated",
            f"Resolved status log → open_escalated (P1 {ticket_id}; auto-resolution paused for senior ownership)",
        )
    )

    context = {
        "account": account,
        "ticket_id": ticket_id,
        "sentiment": sentiment,
        "subject": subject,
        "prior_tickets": prior,
        "recovery_offer": "goodwill credit review on next bill",
    }
    email = draft_response("complaint_escalation", context)
    steps.append(
        actions.make_action(
            "draft_response",
            "Generated empathy + recovery response",
            channel="email",
        )
    )

    return {
        "branch": "complaint_escalation",
        "branch_label": "Complaint / Escalation",
        "steps": steps,
        "email_draft": email,
        "ticket_id": ticket_id,
        "queue": "Retention / Team Lead",
        "summary": (
            f"Raised P1 case {ticket_id}, notified Team Lead, "
            f"set same-day callback."
        ),
    }
