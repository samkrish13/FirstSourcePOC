"""Plan change / upgrade-downgrade remediation branch."""

from __future__ import annotations

import re
from typing import Any

from workflows import actions
from workflows.llm import draft_response


def _extract_plans(text: str) -> tuple[str | None, str | None]:
    """Best-effort current → target plan pair."""
    named = re.findall(r"\b(?:Unlimited|Family)\s+\d{3,4}\b", text, re.I)
    current = named[0] if named else None
    target = named[1] if len(named) > 1 else None

    m = re.search(
        r"\b(?:to|onto)\s+(?:the\s+)?((?:Unlimited|Family)\s+\d{3,4})\b",
        text,
        re.I,
    )
    if m:
        target = m.group(1)

    m = re.search(
        r"\bfrom\s+((?:Unlimited|Family)\s+\d{3,4})\b",
        text,
        re.I,
    )
    if m:
        current = m.group(1)

    return current, target


def run(classification: dict[str, Any], subject: str, body: str) -> dict[str, Any]:
    entities = classification.get("entities") or {}
    account = entities.get("account") or "UNKNOWN"
    combined = f"{subject}\n{body}"
    current_plan, target_plan = _extract_plans(combined)
    if not current_plan and entities.get("plan"):
        current_plan = str(entities["plan"])
    if not target_plan:
        target_plan = "requested plan"

    # POC default: eligible unless hard-block language appears
    eligible = True
    if re.search(r"contract lock|not eligible|outstanding dues", combined, re.I):
        if not re.search(r"no outstanding", combined, re.I):
            eligible = False

    steps: list[dict[str, Any]] = []

    # 1) Eligibility check
    steps.append(
        actions.eligibility_check(
            account=account,
            eligible=eligible,
            current_plan=current_plan,
            target_plan=target_plan,
            reason="No outstanding dues flagged" if eligible else "Eligibility blocked",
        )
    )

    # 2) Catalog quote
    ott_note = None
    if re.search(r"ott|hotstar|disney", combined, re.I):
        ott_note = "OTT bundle may change on Family 499 — confirm in Care order"
    fees_note = "No early-termination fee for cycle-boundary downgrade (POC)"
    monthly_delta = None
    if current_plan and target_plan and current_plan != target_plan:
        monthly_delta = f"{current_plan} → {target_plan}"

    steps.append(
        actions.catalog_quote(
            current_plan=current_plan or "current",
            target_plan=target_plan,
            monthly_delta=monthly_delta,
            fees_note=fees_note,
            ott_note=ott_note,
        )
    )

    # 3) Care order ticket + route + confirmation follow-up
    ticket = actions.create_ticket(
        queue="Care",
        priority="P3",
        summary=f"Plan change {current_plan or '?'} → {target_plan} for {account}",
        eligible=eligible,
        current_plan=current_plan,
        target_plan=target_plan,
    )
    steps.append(ticket)
    ticket_id = ticket["payload"]["ticket_id"]

    steps.append(
        actions.route_to_team("Care", "Plan change order requires Care queue ownership")
    )
    steps.append(
        actions.schedule_follow_up(
            24,
            f"Order confirmation follow-up for Care ticket {ticket_id}",
        )
    )

    context = {
        "account": account,
        "ticket_id": ticket_id,
        "current_plan": current_plan,
        "target_plan": target_plan,
        "eligible": eligible,
        "fees_note": fees_note,
        "ott_note": ott_note,
        "subject": subject,
    }
    email = draft_response("plan_change", context)
    steps.append(
        actions.make_action(
            "draft_response",
            "Generated plan-change confirmation email",
            channel="email",
        )
    )
    steps.append(
        actions.set_resolved_status(
            "open_in_queue",
            f"Resolved status log → open_in_queue (Care order {ticket_id}; confirmation pending)",
        )
    )

    return {
        "branch": "plan_change",
        "branch_label": "Plan Change / Upgrade-Downgrade",
        "steps": steps,
        "email_draft": email,
        "ticket_id": ticket_id,
        "queue": "Care",
        "summary": (
            f"Eligibility={'yes' if eligible else 'no'}; quote "
            f"{current_plan or '?'}→{target_plan}; opened {ticket_id}; "
            f"Care confirmation follow-up."
        ),
    }
