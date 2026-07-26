"""Intake pipeline: classify → branch playbook → act → log."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import db
from workflows import billing, enquiry, escalation, outage, plan_change, sim_port
from workflows.actions import make_action
from workflows.llm import (
    CONFIDENCE_REVIEW_THRESHOLD,
    REQUEST_TYPES,
    classify_request,
)
from workflows.outputs import build_case_outputs

BranchRunner = Callable[[dict[str, Any], str, str], dict[str, Any]]

BRANCHES: dict[str, BranchRunner] = {
    "billing_dispute": billing.run,
    "service_outage": outage.run,
    "complaint_escalation": escalation.run,
    "sim_port": sim_port.run,
    "plan_change": plan_change.run,
    "general_enquiry": enquiry.run,
}


def process_request(
    subject: str,
    body: str,
    request_id: str | None = None,
    force_type: str | None = None,
    *,
    persist: bool = True,
    assigned_to: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    db.init_db()

    classification = classify_request(subject, body)
    if force_type and force_type in REQUEST_TYPES:
        classification = dict(classification)
        classification["request_type"] = force_type
        # Keep natural confidence — do not inflate to hide Needs Review
        classification["rationale"] = (
            str(classification.get("rationale", ""))
            + f" | DEMO override: forced type={force_type}"
        )
        classification["forced_type"] = force_type
        classification["mode"] = "forced"

    request_type = classification.get("request_type", "general_enquiry")
    if request_type not in BRANCHES:
        request_type = "general_enquiry"

    confidence = float(classification.get("confidence", 0.5))
    needs_review = confidence < CONFIDENCE_REVIEW_THRESHOLD
    entities = classification.get("entities") or {}

    case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
    if request_id:
        case_id = f"CASE-{request_id}"
    if not persist:
        case_id = f"COMPARE-{uuid.uuid4().hex[:8].upper()}"

    remediation = BRANCHES[request_type](classification, subject, body)

    if needs_review:
        review_action = make_action(
            "needs_human_review",
            (
                f"Confidence {confidence:.2f} below threshold "
                f"{CONFIDENCE_REVIEW_THRESHOLD} — parked for agent review"
            ),
            threshold=CONFIDENCE_REVIEW_THRESHOLD,
            confidence=confidence,
            human_in_the_loop=True,
            pause_auto_resolution=True,
        )
        remediation["steps"].insert(0, review_action)
        remediation["steps"].append(
            make_action(
                "set_resolved_status",
                "Resolved status log → held_for_review (human-in-the-loop)",
                status="held_for_review",
                resolved_status_log=True,
            )
        )
        remediation["summary"] = "NEEDS REVIEW · " + remediation.get("summary", "")

    # Plain-language next step + SLA due from follow-up actions
    sla_due_at = None
    for step in remediation.get("steps") or []:
        payload = step.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        hours = payload.get("hours")
        if step.get("action_type") in (
            "schedule_follow_up",
            "set_sla_clock",
            "set_callback",
        ) and hours is not None:
            try:
                sla_due_at = db.follow_up_due_iso(float(hours))
            except (TypeError, ValueError):
                pass
            break

    outputs = build_case_outputs(
        classification,
        remediation,
        needs_review=needs_review,
        case_id=case_id,
    )
    remediation["outputs"] = outputs

    status = db.STATUS_ON_HOLD if needs_review else db.STATUS_OPEN
    if persist:
        db.create_case(
            case_id=case_id,
            request_type=request_type,
            urgency=classification.get("urgency"),
            sentiment=classification.get("sentiment"),
            confidence=confidence,
            needs_review=needs_review,
            account=entities.get("account"),
            subject=subject,
            body=body,
            entities=entities,
            classification=classification,
            status=status,
            assigned_to=assigned_to,
            status_updated_by=actor,
            sla_due_at=sla_due_at,
        )

        for i, step in enumerate(remediation["steps"], start=1):
            db.log_action(
                case_id,
                i,
                step.get("action_type", "action"),
                step.get("detail", ""),
                step.get("payload"),
            )

        db.log_action(
            case_id,
            len(remediation["steps"]) + 1,
            "emit_case_outputs",
            "Emitted classification + remediation outputs pack for ops review",
            outputs,
        )

        db.log_message(case_id, body, direction="inbound", channel="email")
        db.log_message(
            case_id,
            remediation.get("email_draft") or "",
            direction="outbound",
            channel="email",
        )

    return {
        "case_id": case_id,
        "classification": classification,
        "needs_review": needs_review,
        "remediation": remediation,
        "outputs": outputs,
        "persisted": persist,
        "status": status,
        "assigned_to": assigned_to,
        "sla_due_at": sla_due_at,
        "status_updated_by": actor,
    }
