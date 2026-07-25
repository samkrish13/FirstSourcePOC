#!/usr/bin/env python3
"""Smoke test: init DB, insert one dummy case + 2 actions + 1 message."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db
from workflows.actions import create_ticket, route_to_team, schedule_follow_up


def main() -> None:
    db.init_db()
    db.clear_all()

    case_id = "CASE-SMOKE-001"
    db.create_case(
        case_id,
        request_type="billing_dispute",
        urgency="medium",
        sentiment="frustrated",
        confidence=0.91,
        needs_review=False,
        account="ACC-784512",
        subject="Charged twice for March postpaid bill",
        body="Dummy smoke-test body for Stage 2.",
        entities={"account": "ACC-784512", "amount": "1299"},
        classification={"request_type": "billing_dispute", "mode": "smoke"},
    )

    holdish = create_ticket(
        queue="Billing",
        priority="P2",
        summary="Duplicate March charge dispute",
    )
    route = route_to_team("Billing", "Contested invoice INV-MAR-784512")
    # schedule_follow_up proves helper shape; not persisted in this smoke path count
    _ = schedule_follow_up(48, "48h billing dispute status check")

    db.log_action(
        case_id,
        step_order=1,
        action_type=holdish["action_type"],
        detail=holdish["detail"],
        payload=holdish["payload"],
    )
    db.log_action(
        case_id,
        step_order=2,
        action_type=route["action_type"],
        detail=route["detail"],
        payload=route["payload"],
    )
    db.log_message(
        case_id,
        content="We have placed a provisional review on the duplicate charge.",
        direction="outbound",
        channel="email",
    )

    cases = db.list_cases()
    print(f"list_cases ({len(cases)}):")
    for row in cases:
        print(
            f"  {row['case_id']} | {row['request_type']} | "
            f"conf={row['confidence']} | review={row['needs_review']}"
        )

    actions = db.get_case_actions(case_id)
    messages = db.get_case_messages(case_id)
    print(f"actions={len(actions)} messages={len(messages)}")
    for a in actions:
        print(f"  step {a['step_order']}: {a['action_type']} — {a['detail']}")
    for m in messages:
        print(f"  msg [{m['direction']}/{m['channel']}]: {m['content'][:60]}...")

    print("OK: smoke_db passed.")


if __name__ == "__main__":
    main()
