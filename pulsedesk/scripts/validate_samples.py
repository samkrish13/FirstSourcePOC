#!/usr/bin/env python3
"""Assert PulseDesk Stage 1 sample inbox integrity."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES_PATH = ROOT / "data" / "sample_requests.json"
BULLETINS_PATH = ROOT / "data" / "outage_bulletins.json"

REQUIRED_BRANCHES = [
    "billing_dispute",
    "service_outage",
    "complaint_escalation",
    "sim_port",
    "plan_change",
    "general_enquiry",
]

REQUIRED_FIELDS = ("id", "branch", "subject", "from", "account", "body")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if not SAMPLES_PATH.exists():
        fail(f"missing {SAMPLES_PATH}")

    data = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))
    golden = data.get("golden") or []
    edge_cases = data.get("edge_cases") or []

    if len(golden) != 6:
        fail(f"expected exactly 6 golden requests, found {len(golden)}")

    branches = [item.get("branch") for item in golden]
    missing = [b for b in REQUIRED_BRANCHES if b not in branches]
    if missing:
        fail(f"missing primary branches: {missing}")

    extras = [b for b in branches if b not in REQUIRED_BRANCHES]
    if extras:
        fail(f"unexpected golden branches: {extras}")

    if len(set(branches)) != 6:
        fail(f"golden branches must be unique; got {branches}")

    for item in golden + edge_cases:
        for field in REQUIRED_FIELDS:
            if not item.get(field):
                fail(f"{item.get('id', '?')} missing field: {field}")

    if len(edge_cases) < 3:
        fail(f"expected ≥3 edge cases, found {len(edge_cases)}")

    for item in edge_cases:
        if item.get("branch") != "ambiguous":
            fail(f"{item.get('id')} edge case branch must be 'ambiguous'")

    if not BULLETINS_PATH.exists():
        fail(f"missing {BULLETINS_PATH}")

    bulletins = json.loads(BULLETINS_PATH.read_text(encoding="utf-8")).get("bulletins") or []
    if not (2 <= len(bulletins) <= 3):
        fail(f"expected 2–3 outage bulletins, found {len(bulletins)}")

    for b in bulletins:
        for field in ("region", "service", "eta_hours", "workaround"):
            if field not in b:
                fail(f"bulletin {b.get('id', '?')} missing field: {field}")

    print("OK: 6 primary branches present; edge cases + bulletins look valid.")
    for item in golden:
        print(f"  {item['id']}: {item['branch']}")


if __name__ == "__main__":
    main()
