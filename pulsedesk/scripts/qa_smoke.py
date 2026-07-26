#!/usr/bin/env python3
"""Pro-tester smoke: functional paths that UI demos depend on."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db
from ui.shell import branch_short, mail_case_row_html
from workflows.pipeline import process_request


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    db.init_db()
    # Don't clear demo DB — unique ids so re-runs don't hit UNIQUE case_id
    run = uuid.uuid4().hex[:6].upper()
    samples = [
        (f"QA-BILL-{run}", "Charged twice for March", "Duplicate charge ACC-784512 ₹1299 INV-1"),
        (f"QA-OUT-{run}", "No 4G in Indiranagar", "Data down since morning pin 560038 ACC-901233"),
        (f"QA-ESC-{run}", "TRAI complaint final warning", "Closing account ACC-556701 speak to manager"),
    ]
    results = []
    for rid, subj, body in samples:
        r = process_request(subj, body, request_id=rid, assigned_to=None, actor="qa")
        results.append(r)
        rem = r.get("remediation") or {}
        steps = rem.get("steps") or []
        types = {s.get("action_type") for s in steps}
        if "draft_response" not in types:
            fail(f"{rid}: missing draft_response")
        if "route_to_team" not in types:
            fail(f"{rid}: missing route_to_team")
        if not any(
            t in types
            for t in ("schedule_follow_up", "set_sla_clock", "set_callback", "close_or_route")
        ):
            fail(f"{rid}: missing follow-up action")
        case = db.get_case(r["case_id"])
        if not case:
            fail(f"{rid}: case not persisted")
        html = mail_case_row_html(case, active=True)
        if "pd-mail-row" not in html or "pd-mail-avatar" not in html:
            fail(f"{rid}: mail row html incomplete")
        if branch_short(str(case.get("request_type") or "")) == "":
            fail(f"{rid}: empty branch short")

    # Claim / unassign
    cid = results[0]["case_id"]
    db.assign_case(cid, "p.sharma", updated_by="QA")
    case = db.get_case(cid)
    assert case and case.get("assigned_to") == "p.sharma"
    mine = db.list_inbox(assigned_to="p.sharma", statuses=[db.STATUS_OPEN, db.STATUS_ON_HOLD, db.STATUS_ESCALATED, db.STATUS_RETURNED])
    if not any(c["case_id"] == cid for c in mine):
        fail("claimed case missing from Mine filter")
    db.assign_case(cid, None, updated_by="QA")
    case = db.get_case(cid)
    assert case and not case.get("assigned_to")

    # Distinct branches for showcase trio
    branches = [r["classification"]["request_type"] for r in results]
    if len(set(branches)) < 3:
        fail(f"expected 3 distinct branches, got {branches}")

    # Released excluded from work statuses
    db.set_case_status(cid, db.STATUS_RELEASED, updated_by="QA")
    unassigned = db.list_inbox(
        unassigned_only=True,
        statuses=[db.STATUS_OPEN, db.STATUS_ON_HOLD, db.STATUS_ESCALATED, db.STATUS_RETURNED],
    )
    if any(c["case_id"] == cid for c in unassigned):
        fail("released case should not appear in active Unassigned filter")

    print("QA PASS: inbox filters, claim, 3-branch remediation, mail HTML")


if __name__ == "__main__":
    main()
