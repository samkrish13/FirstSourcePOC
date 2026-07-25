"""Billing dispute remediation branch."""

from __future__ import annotations

from typing import Any

from workflows import actions
from workflows.llm import draft_response


def run(classification: dict[str, Any], subject: str, body: str) -> dict[str, Any]:
    entities = classification.get("entities") or {}
    account = entities.get("account") or "UNKNOWN"
    amount = entities.get("amount")
    invoice = entities.get("invoice")

    steps: list[dict[str, Any]] = []

    # 1) Provisional hold on contested amount
    steps.append(actions.set_provisional_hold(account, amount))

    # 2) Billing queue ticket
    ticket = actions.create_ticket(
        queue="Billing",
        priority="P2",
        summary=(
            f"Billing dispute for {account}"
            + (f" amount={amount}" if amount else "")
            + (f" invoice={invoice}" if invoice else "")
        ),
        provisional_hold=True,
        invoice=invoice,
        amount=amount,
    )
    steps.append(ticket)
    ticket_id = ticket["payload"]["ticket_id"]

    # 3) Route to Billing + 48h follow-up
    steps.append(
        actions.route_to_team("Billing", "Dispute requires Billing queue ownership")
    )
    steps.append(
        actions.schedule_follow_up(
            48,
            f"48h status follow-up on dispute {ticket_id} for {account}",
        )
    )

    context = {
        "account": account,
        "amount": amount,
        "ticket_id": ticket_id,
        "subject": subject,
        "invoice": invoice,
    }
    email = draft_response("billing_dispute", context)
    steps.append(
        actions.make_action(
            "draft_response",
            "Generated formal acknowledgment email",
            channel="email",
        )
    )
    steps.append(
        actions.set_resolved_status(
            "open_in_queue",
            f"Resolved status log → open_in_queue (Billing dispute {ticket_id})",
        )
    )

    return {
        "branch": "billing_dispute",
        "branch_label": "Billing Dispute",
        "steps": steps,
        "email_draft": email,
        "ticket_id": ticket_id,
        "queue": "Billing",
        "summary": (
            f"Opened {ticket_id}, set provisional hold"
            + (f" for {amount}" if amount else "")
            + ", routed to Billing, scheduled 48h follow-up."
        ),
    }
