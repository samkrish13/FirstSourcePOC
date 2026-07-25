"""General enquiry remediation branch."""

from __future__ import annotations

import re
from typing import Any

from workflows import actions
from workflows.llm import draft_response

FAQ_LINKS = {
    "roaming": "https://help.pulsedesk.example/international-roaming",
    "esim": "https://help.pulsedesk.example/esim-roaming",
    "default": "https://help.pulsedesk.example/faq",
}


def _topic_and_link(text: str) -> tuple[str, str]:
    lower = text.lower()
    if "roaming" in lower or "singapore" in lower or "international" in lower:
        return "international_roaming", FAQ_LINKS["roaming"]
    if "esim" in lower:
        return "esim", FAQ_LINKS["esim"]
    return "general_faq", FAQ_LINKS["default"]


def run(classification: dict[str, Any], subject: str, body: str) -> dict[str, Any]:
    entities = classification.get("entities") or {}
    account = entities.get("account") or "UNKNOWN"
    combined = f"{subject}\n{body}"
    topic, link = _topic_and_link(combined)

    steps: list[dict[str, Any]] = []

    # 1) FAQ / self-serve
    steps.append(actions.faq_self_serve(link, topic=topic))

    # 2) Light General tracking ticket
    ticket = actions.create_ticket(
        queue="General",
        priority="P4",
        summary=f"General enquiry ({topic}) for {account}",
        topic=topic,
        faq_link=link,
    )
    steps.append(ticket)
    ticket_id = ticket["payload"]["ticket_id"]

    # 3) Route to General + close-or-route disposition
    steps.append(
        actions.route_to_team("General", "Informational enquiry — General queue tracking")
    )

    # Close if clearly answered via self-serve how-to; else note specialist route option
    can_close = bool(re.search(r"how do i|help article|link to the help", combined, re.I))
    disposition = "close" if can_close else "route_specialist"
    steps.append(
        actions.make_action(
            "close_or_route",
            (
                f"Disposition={disposition}: self-serve link provided"
                if can_close
                else f"Disposition={disposition}: may need specialist if FAQ insufficient"
            ),
            disposition=disposition,
            faq_link=link,
            topic=topic,
        )
    )
    if can_close:
        steps.append(
            actions.set_resolved_status(
                "resolved",
                f"Resolved status log → resolved ({topic}; FAQ self-serve sufficient)",
            )
        )
    else:
        steps.append(
            actions.set_resolved_status(
                "open_in_queue",
                f"Resolved status log → open_in_queue ({topic}; specialist may be required)",
            )
        )

    context = {
        "account": account,
        "ticket_id": ticket_id,
        "faq_link": link,
        "topic": topic,
        "disposition": disposition,
        "subject": subject,
    }
    email = draft_response("general_enquiry", context)
    steps.append(
        actions.make_action(
            "draft_response",
            "Generated FAQ / how-to response email",
            channel="email",
        )
    )

    return {
        "branch": "general_enquiry",
        "branch_label": "General Enquiry",
        "steps": steps,
        "email_draft": email,
        "ticket_id": ticket_id,
        "queue": "General",
        "summary": (
            f"Provided FAQ ({topic}); opened {ticket_id}; "
            f"disposition={disposition}."
        ),
    }
