"""Optional SQLite log of analyst runs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "data" / "signalforge.db"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,
                final_score INTEGER,
                priority TEXT,
                result_json TEXT,
                created_at TEXT
            )
            """
        )


def save_run(customer_id: str, result: dict[str, Any]) -> None:
    init_db()
    serializable = {
        k: v
        for k, v in result.items()
        if k not in ("transactions", "activity")
    }
    # store lightweight frames as records
    serializable["transactions"] = result["transactions"].to_dict(orient="records")
    serializable["activity"] = result["activity"].to_dict(orient="records")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO runs (customer_id, final_score, priority, result_json, created_at) VALUES (?,?,?,?,?)",
            (
                customer_id,
                result["final_score"],
                result["priority"],
                json.dumps(serializable, default=str),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, customer_id, final_score, priority, created_at FROM runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
