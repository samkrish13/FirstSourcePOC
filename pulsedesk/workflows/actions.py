"""Shared remediation action primitives for PulseDesk playbooks."""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from typing import Any

_ticket_counter = itertools.count(1001)

QUEUE_PREFIX: dict[str, str] = {
    "Billing": "BIL",
    "Network Ops": "NET",
    "Network Comms": "NCM",
    "Retention": "RET",
    "Port/SIM": "SIM",
    "Care": "CARE",
    "General": "GEN",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def next_ticket(prefix: str) -> str:
    return f"{prefix}-{next(_ticket_counter)}"


def make_action(
    action_type: str,
    detail: str,
    payload: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(payload or {})
    merged.update(extra)
    return {
        "action_type": action_type,
        "detail": detail,
        "payload": merged,
        "timestamp": _now().isoformat(),
    }


def create_ticket(
    queue: str,
    priority: str,
    summary: str,
    **extra: Any,
) -> dict[str, Any]:
    prefix = QUEUE_PREFIX.get(queue, "TCK")
    ticket_id = next_ticket(prefix)
    return make_action(
        "create_ticket",
        f"Created {priority} ticket {ticket_id} in {queue}: {summary}",
        ticket_id=ticket_id,
        queue=queue,
        priority=priority,
        summary=summary,
        **extra,
    )


def route_to_team(team: str, reason: str) -> dict[str, Any]:
    return make_action(
        "route_to_team",
        f"Routed to {team}: {reason}",
        team=team,
        reason=reason,
    )


def schedule_follow_up(hours: int, note: str) -> dict[str, Any]:
    due = _now() + timedelta(hours=hours)
    return make_action(
        "schedule_follow_up",
        note,
        due_at=due.isoformat(),
        hours=hours,
    )


def notify_lead(channel: str, message: str) -> dict[str, Any]:
    """Team-lead / supervisor notification (simulated Slack/email)."""
    return make_action(
        "notify_lead",
        f"Supervisor alert — notified Team Lead via {channel}",
        channel=channel,
        message=message,
        supervisor_alert=True,
        notification=True,
    )


def supervisor_alert(
    message: str,
    *,
    channels: str = "slack+email",
) -> dict[str, Any]:
    """Explicit supervisor alert artifact for urgent / escalation paths."""
    return make_action(
        "supervisor_alert",
        f"Supervisor alert dispatched via {channels}",
        message=message,
        channels=channels,
        supervisor_alert=True,
        notification=True,
        pause_auto_resolution=True,
    )


def set_provisional_hold(account: str, amount: str | None = None) -> dict[str, Any]:
    detail = f"Provisional billing hold set on {account}"
    if amount:
        detail += f" for {amount}"
    return make_action(
        "set_provisional_hold",
        detail,
        account=account,
        amount=amount,
        hold=True,
    )


def set_sla_clock(severity: str, hours: int) -> dict[str, Any]:
    due = _now() + timedelta(hours=hours)
    return make_action(
        "set_sla_clock",
        f"SLA flag set ({severity}), due in {hours}h",
        severity=severity,
        due_at=due.isoformat(),
        hours=hours,
        sla_flag=True,
        flag="SLA_ACTIVE",
    )


def set_resolved_status(status: str, note: str | None = None) -> dict[str, Any]:
    """Persist resolved / open / held status for the case log."""
    detail = note or f"Resolved status log → {status}"
    return make_action(
        "set_resolved_status",
        detail,
        status=status,
        resolved_status_log=True,
    )


def set_callback(same_day: bool = True, note: str | None = None) -> dict[str, Any]:
    due = _now() + timedelta(hours=4 if same_day else 24)
    detail = note or (
        "Same-day callback task created" if same_day else "Callback task created"
    )
    return make_action(
        "set_callback",
        detail,
        due_at=due.isoformat(),
        same_day=same_day,
    )


def match_outage(bulletin: dict[str, Any] | None) -> dict[str, Any]:
    if bulletin:
        bulletin_id = bulletin.get("id", "unknown")
        region = bulletin.get("region", "")
        return make_action(
            "match_outage",
            f"Matched bulletin {bulletin_id}" + (f" — {region}" if region else ""),
            matched=True,
            bulletin_id=bulletin_id,
            region=region,
            service=bulletin.get("service"),
            eta_hours=bulletin.get("eta_hours"),
            workaround=bulletin.get("workaround"),
        )
    return make_action(
        "match_outage",
        "No matching outage bulletin — escalate to Network Ops",
        matched=False,
    )


def faq_self_serve(link: str, topic: str | None = None) -> dict[str, Any]:
    detail = f"Provided self-serve guidance: {link}"
    if topic:
        detail = f"Provided self-serve guidance for {topic}: {link}"
    return make_action(
        "faq_self_serve",
        detail,
        link=link,
        topic=topic,
    )


def identity_checklist(
    *,
    account: str,
    kyc_complete: bool,
    sim_kit_id: str | None = None,
    upc: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    status = "passed" if kyc_complete else "incomplete"
    detail = f"Identity checklist {status} for {account}"
    if notes:
        detail = f"{detail}: {notes}"
    return make_action(
        "identity_checklist",
        detail,
        account=account,
        kyc_complete=kyc_complete,
        sim_kit_id=sim_kit_id,
        upc=upc,
        status=status,
    )


def eligibility_check(
    *,
    account: str,
    eligible: bool,
    current_plan: str | None = None,
    target_plan: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    status = "eligible" if eligible else "not_eligible"
    detail = f"Plan change eligibility {status} for {account}"
    if reason:
        detail = f"{detail}: {reason}"
    return make_action(
        "eligibility_check",
        detail,
        account=account,
        eligible=eligible,
        current_plan=current_plan,
        target_plan=target_plan,
        reason=reason,
    )


def catalog_quote(
    *,
    current_plan: str,
    target_plan: str,
    monthly_delta: str | None = None,
    fees_note: str | None = None,
    ott_note: str | None = None,
) -> dict[str, Any]:
    detail = f"Catalog quote: {current_plan} → {target_plan}"
    if monthly_delta:
        detail = f"{detail} ({monthly_delta})"
    return make_action(
        "catalog_quote",
        detail,
        current_plan=current_plan,
        target_plan=target_plan,
        monthly_delta=monthly_delta,
        fees_note=fees_note,
        ott_note=ott_note,
    )
