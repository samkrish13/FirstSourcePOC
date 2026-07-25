#!/usr/bin/env python3
"""Run all 6 golden samples (+ ambiguous edges) and write demo artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db  # noqa: E402
from workflows.llm import CONFIDENCE_REVIEW_THRESHOLD, REQUEST_TYPES  # noqa: E402
from workflows.pipeline import process_request  # noqa: E402

SAMPLES_PATH = ROOT / "data" / "sample_requests.json"
OUT_JSON = ROOT / "screenshots" / "demo_outputs.json"
OUT_LOG = ROOT / "screenshots" / "sample_run_log.txt"

GOLDEN_ORDER = list(REQUEST_TYPES)

# Signature actions that must appear for each golden branch (distinct playbooks)
SIGNATURES: dict[str, set[str]] = {
    "billing_dispute": {"set_provisional_hold", "schedule_follow_up"},
    "service_outage": {"match_outage", "set_sla_clock"},
    "complaint_escalation": {"notify_lead", "set_callback"},
    "sim_port": {"identity_checklist"},
    "plan_change": {"eligibility_check", "catalog_quote"},
    "general_enquiry": {"faq_self_serve", "close_or_route"},
}


def _action_types(result: dict) -> set[str]:
    steps = (result.get("remediation") or {}).get("steps") or []
    return {s.get("action_type", "") for s in steps if s.get("action_type")}


def _record(
    *,
    sample: dict,
    result: dict,
    expected_branch: str | None,
) -> dict:
    rem = result["remediation"]
    types = _action_types(result)
    classified = result["classification"]["request_type"]
    ok_class = expected_branch is None or classified == expected_branch
    return {
        "sample_id": sample["id"],
        "expected_branch": expected_branch,
        "classified_as": classified,
        "classification_ok": ok_class,
        "case_id": result["case_id"],
        "needs_review": result["needs_review"],
        "confidence": result["classification"].get("confidence"),
        "action_types": sorted(types),
        "steps": [
            {"action_type": s.get("action_type"), "detail": s.get("detail")}
            for s in rem.get("steps") or []
        ],
        "ticket_id": rem.get("ticket_id"),
        "queue": rem.get("queue"),
        "summary": rem.get("summary"),
        "email_draft": rem.get("email_draft"),
    }


def _append_log(log_lines: list[str], block: dict, rem_steps: list[dict]) -> None:
    log_lines.append("")
    log_lines.append(
        f"[{block['sample_id']}] expected={block['expected_branch']} "
        f"got={block['classified_as']}"
    )
    log_lines.append(
        f"  case_id={block['case_id']} conf={block['confidence']} "
        f"needs_review={block['needs_review']} ok={block['classification_ok']}"
    )
    log_lines.append(f"  queue={block['queue']} ticket={block['ticket_id']}")
    log_lines.append(f"  summary={block['summary']}")
    log_lines.append(f"  action_types={block['action_types']}")
    for s in rem_steps:
        log_lines.append(f"    - {s.get('action_type')}: {s.get('detail')}")
    log_lines.append("  --- email draft ---")
    log_lines.append(block.get("email_draft") or "")
    log_lines.append("  -------------------")


def main() -> None:
    data = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))
    golden_by_branch = {item["branch"]: item for item in data["golden"]}
    edge_cases = data.get("edge_cases") or []

    missing = [b for b in GOLDEN_ORDER if b not in golden_by_branch]
    if missing:
        print(f"FAIL: missing golden samples for {missing}", file=sys.stderr)
        sys.exit(1)

    db.init_db()
    db.clear_all()

    outputs: list[dict] = []
    log_lines: list[str] = [
        "PulseDesk Stage 7 — all six branches + ambiguous edges",
        "=" * 60,
    ]
    type_sets: dict[str, set[str]] = {}
    failures: list[str] = []

    # --- Golden 6 ---
    for branch in GOLDEN_ORDER:
        sample = golden_by_branch[branch]
        result = process_request(
            sample["subject"],
            sample["body"],
            request_id=sample["id"],
        )
        block = _record(sample=sample, result=result, expected_branch=branch)
        types = set(block["action_types"])
        type_sets[branch] = types
        outputs.append(block)
        _append_log(log_lines, block, result["remediation"].get("steps") or [])

        print(
            f"{sample['id']}: {branch} → {block['classified_as']} | "
            f"review={block['needs_review']} | types={block['action_types']} | "
            f"ticket={block['ticket_id']}"
        )

        if not block["classification_ok"]:
            failures.append(
                f"{sample['id']}: expected {branch}, got {block['classified_as']}"
            )
        required = SIGNATURES[branch]
        if not required.issubset(types):
            failures.append(
                f"{sample['id']}: missing signature actions "
                f"{sorted(required - types)}; got {sorted(types)}"
            )

    # --- Ambiguous edges ---
    log_lines.append("")
    log_lines.append("Ambiguous edge cases")
    log_lines.append("-" * 40)
    for sample in edge_cases:
        result = process_request(
            sample["subject"],
            sample["body"],
            request_id=sample["id"],
        )
        block = _record(sample=sample, result=result, expected_branch=None)
        block["expected_branch"] = "ambiguous"
        outputs.append(block)
        _append_log(log_lines, block, result["remediation"].get("steps") or [])

        review_ok = block["needs_review"] or (
            float(block["confidence"] or 1.0) < CONFIDENCE_REVIEW_THRESHOLD
        )
        has_review_action = "needs_human_review" in set(block["action_types"])
        print(
            f"{sample['id']}: ambiguous → {block['classified_as']} | "
            f"conf={block['confidence']} review={block['needs_review']} "
            f"action={has_review_action}"
        )
        if not (review_ok and has_review_action):
            failures.append(
                f"{sample['id']}: ambiguous sample must needs_review "
                f"with needs_human_review action "
                f"(conf={block['confidence']}, review={block['needs_review']})"
            )

    # Distinct timelines across showcase trio (still required)
    if not (
        type_sets["billing_dispute"]
        != type_sets["service_outage"]
        != type_sets["complaint_escalation"]
        != type_sets["billing_dispute"]
    ):
        failures.append("showcase trio action_type sets are not pairwise distinct")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(outputs, indent=2), encoding="utf-8")
    OUT_LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    print(f"\nWrote {OUT_JSON}")
    print(f"Wrote {OUT_LOG}")

    if failures:
        print("GATE FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)

    print("GATE PASSED: all 6 golden branches + ambiguous review lane.")


if __name__ == "__main__":
    main()
