"""Run SignalForge aggregation for showcase customers and write outputs."""
from __future__ import annotations

import json
from pathlib import Path

from ingest import load_sources, customer_bundle
from summarize import aggregate_customer
import db

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "screenshots" / "demo_outputs.json"
LOG = ROOT / "screenshots" / "sample_run_log.txt"
MEMO_DIR = ROOT / "screenshots" / "memos"


def main() -> None:
    db.init_db()
    sources = load_sources()
    showcase = ["CUS-1001", "CUS-1002", "CUS-1003"]
    results = []
    lines = ["SignalForge Demo Run Log", "=" * 60, ""]
    MEMO_DIR.mkdir(parents=True, exist_ok=True)

    for cid in showcase:
        bundle = customer_bundle(cid, sources)
        result = aggregate_customer(bundle)
        db.save_run(cid, result)
        slim = {
            "customer_id": cid,
            "name": result["profile"].get("name"),
            "final_score": result["final_score"],
            "priority": result["priority"],
            "rule_score": result["rule_score"],
            "adjustment": result["llm"].get("adjustment"),
            "factors": result["factors"],
            "red_flags": result["llm"].get("red_flags"),
            "recommended_actions": result["llm"].get("recommended_actions"),
            "memo": result["memo"],
        }
        results.append(slim)
        (MEMO_DIR / f"{cid}_memo.txt").write_text(result["memo"], encoding="utf-8")
        lines.append(f"{cid} · {result['profile'].get('name')}")
        lines.append(f"  Priority={result['priority']} Score={result['final_score']}")
        lines.append(f"  Rule={result['rule_score']} Adj={result['llm'].get('adjustment')}")
        for f in result["factors"][:5]:
            lines.append(f"  Factor: {f['factor']} ({f['points']:+d}) — {f['why']}")
        lines.append("")

    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    LOG.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"Wrote {LOG}")
    for r in results:
        print(f"{r['customer_id']}: {r['priority']} {r['final_score']}")


if __name__ == "__main__":
    main()
