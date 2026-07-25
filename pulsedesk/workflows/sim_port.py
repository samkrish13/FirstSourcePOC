"""SIM / Port / Number Change remediation branch."""

from __future__ import annotations

import re
from typing import Any

from workflows import actions
from workflows.llm import draft_response


def _extract_upc(text: str) -> str | None:
    m = re.search(r"\bUPC(?:\s+code)?\s*[:=]?\s*(\d{6,})\b", text, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\bupc\s+(\d{6,})\b", text, re.I)
    return m.group(1) if m else None


def _extract_sim_kit(text: str) -> str | None:
    m = re.search(r"\bSIM[- ]?\d{4,}\b", text, re.I)
    return m.group(0).upper().replace(" ", "-") if m else None


def run(classification: dict[str, Any], subject: str, body: str) -> dict[str, Any]:
    entities = classification.get("entities") or {}
    account = entities.get("account") or "UNKNOWN"
    combined = f"{subject}\n{body}"
    upc = _extract_upc(combined)
    sim_kit = _extract_sim_kit(combined)
    kyc_complete = bool(
        re.search(r"\b(e?kyc|aadhaar|identity verification)\b", combined, re.I)
    )

    steps: list[dict[str, Any]] = []

    # 1) Identity checklist
    steps.append(
        actions.identity_checklist(
            account=account,
            kyc_complete=kyc_complete,
            sim_kit_id=sim_kit,
            upc=upc,
            notes="Store eKYC present" if kyc_complete else "KYC incomplete — verify before activate",
        )
    )

    # 2) Port/SIM ticket
    ticket = actions.create_ticket(
        queue="Port/SIM",
        priority="P2",
        summary=(
            f"SIM/port activation for {account}"
            + (f" UPC={upc}" if upc else "")
            + (f" kit={sim_kit}" if sim_kit else "")
        ),
        upc=upc,
        sim_kit_id=sim_kit,
    )
    steps.append(ticket)
    ticket_id = ticket["payload"]["ticket_id"]

    # 3) Route + 24h status follow-up
    steps.append(
        actions.route_to_team(
            "Port/SIM",
            "MNP/SIM activation requires Port/SIM queue ownership",
        )
    )
    steps.append(
        actions.schedule_follow_up(
            24,
            f"24h port/activation status follow-up for {ticket_id}",
        )
    )

    context = {
        "account": account,
        "ticket_id": ticket_id,
        "upc": upc,
        "sim_kit_id": sim_kit,
        "kyc_complete": kyc_complete,
        "subject": subject,
    }
    email = draft_response("sim_port", context)
    steps.append(
        actions.make_action(
            "draft_response",
            "Generated port/activation status email",
            channel="email",
        )
    )
    steps.append(
        actions.set_resolved_status(
            "open_in_queue",
            f"Resolved status log → open_in_queue (Port/SIM {ticket_id})",
        )
    )

    return {
        "branch": "sim_port",
        "branch_label": "SIM / Port / Number Change",
        "steps": steps,
        "email_draft": email,
        "ticket_id": ticket_id,
        "queue": "Port/SIM",
        "summary": (
            f"Identity checklist for {account}; opened {ticket_id}; "
            f"routed Port/SIM; 24h status follow-up."
        ),
    }
