"""Service outage / technical fault remediation branch."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from workflows import actions
from workflows.llm import draft_response

BULLETINS_PATH = Path(__file__).resolve().parent.parent / "data" / "outage_bulletins.json"


def _load_bulletins() -> list[dict[str, Any]]:
    data = json.loads(BULLETINS_PATH.read_text(encoding="utf-8"))
    return list(data.get("bulletins") or [])


def _region_tokens(region: str) -> list[str]:
    parts = re.split(r"[/(),]+", region)
    tokens: list[str] = []
    for part in parts:
        part = part.strip().lower()
        if not part:
            continue
        tokens.append(part)
        tokens.extend(t for t in part.split() if len(t) >= 4 or t.isdigit())
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _match_bulletin(
    subject: str,
    body: str,
    entities: dict[str, Any],
) -> dict[str, Any] | None:
    text = f"{subject}\n{body}".lower()
    location = (entities.get("location") or "").lower()
    best: dict[str, Any] | None = None
    best_score = 0

    for bulletin in _load_bulletins():
        if str(bulletin.get("status", "")).lower() == "resolved":
            continue

        score = 0
        region = str(bulletin.get("region", ""))
        for token in _region_tokens(region):
            if token in text or token in location:
                score += 2 if token.isdigit() or len(token) >= 6 else 1

        service = str(bulletin.get("service", "")).lower()
        for hint in ("4g", "5g", "data", "volte", "voice", "sms", "broadband"):
            if hint in service and hint in text:
                score += 1

        if score > best_score:
            best_score = score
            best = bulletin

    return best if best_score >= 2 else None


def run(classification: dict[str, Any], subject: str, body: str) -> dict[str, Any]:
    entities = classification.get("entities") or {}
    account = entities.get("account") or "UNKNOWN"
    bulletin = _match_bulletin(subject, body, entities)

    steps: list[dict[str, Any]] = []
    steps.append(actions.match_outage(bulletin))

    ticket_id: str | None = None

    if bulletin:
        eta = int(bulletin.get("eta_hours") or 4)
        severity = str(bulletin.get("severity") or "major")
        steps.append(actions.set_sla_clock(severity, eta))
        steps.append(
            actions.route_to_team(
                "Network Comms",
                f"Matched active bulletin {bulletin.get('id')}",
            )
        )
        context = {
            "account": account,
            "bulletin_id": bulletin.get("id"),
            "eta_hours": eta,
            "workaround": bulletin.get("workaround"),
            "location": entities.get("location") or bulletin.get("region"),
        }
        queue = "Network Comms"
        summary = (
            f"Matched bulletin {bulletin.get('id')}; routed Network Comms; "
            f"SLA clock ~{eta}h ETA."
        )
    else:
        ticket = actions.create_ticket(
            queue="Network Ops",
            priority="P2",
            summary=f"Unmatched service fault for {account}",
            location=entities.get("location"),
        )
        steps.append(ticket)
        ticket_id = ticket["payload"]["ticket_id"]
        steps.append(
            actions.route_to_team("Network Ops", "No active bulletin match")
        )
        steps.append(actions.set_sla_clock("high", 8))
        context = {
            "account": account,
            "ticket_id": ticket_id,
            "location": entities.get("location"),
        }
        queue = "Network Ops"
        summary = f"No bulletin match; routed {ticket_id} to Network Ops with 8h SLA."

    email = draft_response("service_outage", context)
    steps.append(
        actions.make_action(
            "draft_response",
            "Generated outage/status response email",
            channel="email",
            email_draft=email,
        )
    )
    steps.append(
        actions.set_resolved_status(
            "open_in_queue",
            f"Resolved status log → open_in_queue (Network {queue}"
            + (f"; ticket {ticket_id}" if ticket_id else "")
            + "; SLA flag active)",
        )
    )

    return {
        "branch": "service_outage",
        "branch_label": "Service Outage / Technical Fault",
        "steps": steps,
        "email_draft": email,
        "ticket_id": ticket_id,
        "bulletin_id": (bulletin or {}).get("id") if bulletin else None,
        "queue": queue,
        "summary": summary,
    }
