"""Assemble brief-aligned case outputs from classification + remediation."""

from __future__ import annotations

from typing import Any

from workflows.llm import BRANCH_LABELS


def _payload(step: dict[str, Any]) -> dict[str, Any]:
    p = step.get("payload")
    return p if isinstance(p, dict) else {}


def build_case_outputs(
    classification: dict[str, Any],
    remediation: dict[str, Any],
    *,
    needs_review: bool,
    case_id: str,
) -> dict[str, Any]:
    """Structured outputs matching the challenge expected format."""
    steps = list(remediation.get("steps") or [])
    draft = (remediation.get("email_draft") or "").strip()
    request_type = classification.get("request_type") or remediation.get("branch") or ""

    routing_notification = None
    supervisor_alert = None
    sla_flag = None
    follow_up_task = None
    resolved_status = None
    confirmation_message = None

    for step in steps:
        action = step.get("action_type") or ""
        detail = str(step.get("detail") or "")
        p = _payload(step)

        if action == "route_to_team":
            team = p.get("team") or remediation.get("queue") or "queue"
            routing_notification = (
                f"ROUTING NOTIFICATION → {team}: {p.get('reason') or detail}"
            )
        elif action in ("notify_lead", "supervisor_alert"):
            supervisor_alert = (
                f"SUPERVISOR ALERT ({p.get('channel') or p.get('channels') or 'ops'}): "
                f"{p.get('message') or detail}"
            )
        elif action == "set_sla_clock":
            sla_flag = {
                "flag": "SLA_ACTIVE",
                "severity": p.get("severity"),
                "hours": p.get("hours"),
                "due_at": p.get("due_at"),
                "detail": detail,
            }
            if not follow_up_task:
                follow_up_task = detail
        elif action in ("schedule_follow_up", "set_callback"):
            follow_up_task = detail
        elif action == "set_resolved_status":
            resolved_status = str(p.get("status") or detail)
        elif action == "close_or_route":
            if p.get("disposition") == "close":
                resolved_status = "resolved"
                confirmation_message = (
                    confirmation_message
                    or f"Case marked resolved via self-serve ({p.get('topic') or 'FAQ'})."
                )
            else:
                resolved_status = resolved_status or "open_in_queue"
        elif action == "draft_response" and not confirmation_message:
            confirmation_message = "Customer confirmation / acknowledgement draft generated."

    if draft and not confirmation_message:
        first = next((ln.strip() for ln in draft.splitlines() if ln.strip()), "")
        confirmation_message = first[:220] if first else "Draft acknowledgement ready."

    if needs_review:
        human_in_the_loop = True
        human_in_the_loop_flag = "HUMAN_IN_THE_LOOP — auto-resolution paused; hold outbound send"
        resolved_status = "held_for_review"
    else:
        human_in_the_loop = False
        human_in_the_loop_flag = "AUTO_OK — confidence above review gate"
        if not resolved_status:
            resolved_status = "open_in_queue"

    # Escalations always imply senior ownership even when confidence is high
    if request_type == "complaint_escalation" and not supervisor_alert:
        supervisor_alert = (
            f"SUPERVISOR ALERT: P1 escalation path for case {case_id} "
            f"(queue={remediation.get('queue')})."
        )

    return {
        "classification_label": BRANCH_LABELS.get(request_type, request_type),
        "urgency": classification.get("urgency") or "—",
        "confidence": classification.get("confidence"),
        "action_summary": [str(s.get("action_type") or "action") for s in steps],
        "draft_response": draft,
        "routing_notification": routing_notification,
        "supervisor_alert": supervisor_alert,
        "confirmation_message": confirmation_message,
        "sla_flag": sla_flag,
        "follow_up_task": follow_up_task,
        "human_in_the_loop": human_in_the_loop,
        "human_in_the_loop_flag": human_in_the_loop_flag,
        "resolved_status": resolved_status,
        "case_log_entry": case_id,
        "ticket_id": remediation.get("ticket_id"),
        "queue": remediation.get("queue"),
    }
