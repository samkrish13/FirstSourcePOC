#!/usr/bin/env python3
"""Classify the 6 golden sample requests and print type / confidence / entities."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflows.llm import classify_request  # noqa: E402

SAMPLES_PATH = ROOT / "data" / "sample_requests.json"


def main() -> None:
    data = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))
    golden = data["golden"]
    failures: list[str] = []

    print("PulseDesk classify demo (heuristic / LLM)\n")
    for item in golden:
        result = classify_request(item["subject"], item["body"])
        expected = item["branch"]
        got = result["request_type"]
        ok = got == expected
        mark = "OK" if ok else "FAIL"
        if not ok:
            failures.append(f"{item['id']}: expected {expected}, got {got}")

        print(
            f"[{mark}] {item['id']}  expected={expected}  "
            f"got={got}  conf={result['confidence']}  mode={result['mode']}"
        )
        print(f"       entities={result['entities']}")
        print(f"       rationale={result['rationale'][:120]}")
        print()

    if failures:
        print("GATE FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("GATE PASSED: all 6 golden samples mapped to expected branches.")


if __name__ == "__main__":
    main()
