"""SQLite audit trail for PulseDesk cases, actions, and messages."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent / "data"


def _resolve_db_path() -> Path:
    """Prefer repo data/; fall back to /tmp if the tree is not writable (some hosts)."""
    primary = _DATA_DIR / "pulsedesk.db"
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = _DATA_DIR / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return primary
    except OSError:
        alt_dir = Path(tempfile.gettempdir()) / "pulsedesk"
        alt_dir.mkdir(parents=True, exist_ok=True)
        return alt_dir / "pulsedesk.db"


DB_PATH = Path(os.environ.get("PULSEDESK_DB_PATH") or _resolve_db_path())

# Agent-familiar case lifecycle
STATUS_OPEN = "open"
STATUS_ON_HOLD = "on_hold"
STATUS_ESCALATED = "escalated"
STATUS_RELEASED = "released"
STATUS_RETURNED = "returned"

STATUS_LABELS = {
    STATUS_OPEN: "Open",
    STATUS_ON_HOLD: "On hold",
    STATUS_ESCALATED: "Escalated",
    STATUS_RELEASED: "Released",
    STATUS_RETURNED: "Returned",
}


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_case_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(cases)")}
    migrations = [
        ("status", "TEXT DEFAULT 'open'"),
        ("assigned_to", "TEXT"),
        ("status_updated_at", "TEXT"),
        ("status_updated_by", "TEXT"),
        ("escalate_reason", "TEXT"),
        ("return_reason", "TEXT"),
        ("lead_note_to_agent", "TEXT"),
        ("sla_due_at", "TEXT"),
        ("received_at", "TEXT"),
    ]
    for name, decl in migrations:
        if name not in cols:
            conn.execute(f"ALTER TABLE cases ADD COLUMN {name} {decl}")


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT UNIQUE NOT NULL,
                request_type TEXT NOT NULL,
                urgency TEXT,
                sentiment TEXT,
                confidence REAL,
                needs_review INTEGER DEFAULT 0,
                account TEXT,
                subject TEXT,
                body TEXT,
                entities_json TEXT,
                classification_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                step_order INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                detail TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                channel TEXT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        _ensure_case_columns(conn)
        conn.execute(
            """
            UPDATE cases SET status = 'on_hold'
            WHERE needs_review = 1
              AND COALESCE(status, 'open') IN ('open', '')
              AND case_id NOT IN (
                SELECT DISTINCT a.case_id FROM actions a
                WHERE a.action_type = 'agent_escalated_to_lead'
              )
            """
        )
        conn.execute(
            """
            UPDATE cases SET status = 'escalated'
            WHERE case_id IN (
              SELECT DISTINCT a.case_id FROM actions a
              WHERE a.action_type = 'agent_escalated_to_lead'
            )
            AND COALESCE(status, '') NOT IN ('released', 'returned')
            AND NOT EXISTS (
              SELECT 1 FROM actions a2
              WHERE a2.case_id = cases.case_id
                AND a2.action_type IN ('lead_approved_release', 'lead_returned_to_agent')
                AND a2.id > (
                  SELECT MAX(a3.id) FROM actions a3
                  WHERE a3.case_id = cases.case_id
                    AND a3.action_type = 'agent_escalated_to_lead'
                )
            )
            """
        )


def create_case(
    case_id: str,
    request_type: str,
    *,
    urgency: str | None = None,
    sentiment: str | None = None,
    confidence: float | None = None,
    needs_review: bool = False,
    account: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    entities: dict[str, Any] | None = None,
    classification: dict[str, Any] | None = None,
    status: str | None = None,
    assigned_to: str | None = None,
    status_updated_by: str | None = None,
    sla_due_at: str | None = None,
    received_at: str | None = None,
) -> None:
    now = _now()
    case_status = status or (STATUS_ON_HOLD if needs_review else STATUS_OPEN)
    with _connect() as conn:
        _ensure_case_columns(conn)
        conn.execute(
            """
            INSERT INTO cases (
                case_id, request_type, urgency, sentiment, confidence,
                needs_review, account, subject, body,
                entities_json, classification_json, created_at,
                status, assigned_to, status_updated_at, status_updated_by,
                sla_due_at, received_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                request_type,
                urgency,
                sentiment,
                confidence,
                1 if needs_review else 0,
                account,
                subject,
                body,
                json.dumps(entities or {}),
                json.dumps(classification or {}),
                now,
                case_status,
                assigned_to,
                now,
                status_updated_by,
                sla_due_at,
                received_at or now,
            ),
        )


def log_action(
    case_id: str,
    step_order: int,
    action_type: str,
    detail: str,
    payload: dict[str, Any] | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO actions (
                case_id, step_order, action_type, detail, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                step_order,
                action_type,
                detail,
                json.dumps(payload or {}),
                _now(),
            ),
        )


def log_message(
    case_id: str,
    content: str,
    *,
    direction: str = "outbound",
    channel: str = "email",
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO messages (case_id, direction, channel, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (case_id, direction, channel, content, _now()),
        )


def list_cases(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        _ensure_case_columns(conn)
        rows = conn.execute(
            "SELECT * FROM cases ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_inbox(
    *,
    assigned_to: str | None = None,
    unassigned_only: bool = False,
    statuses: list[str] | None = None,
    limit: int = 80,
) -> list[dict[str, Any]]:
    """Work queue — filter by assignment and lifecycle status."""
    clauses: list[str] = []
    params: list[Any] = []
    if unassigned_only:
        clauses.append("(assigned_to IS NULL OR assigned_to = '')")
    elif assigned_to:
        clauses.append("assigned_to = ?")
        params.append(assigned_to)
    if statuses:
        placeholders = ",".join("?" * len(statuses))
        clauses.append(f"status IN ({placeholders})")
        params.extend(statuses)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _connect() as conn:
        _ensure_case_columns(conn)
        rows = conn.execute(
            f"""
            SELECT * FROM cases
            {where}
            ORDER BY COALESCE(received_at, created_at) DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_case(case_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        _ensure_case_columns(conn)
        row = conn.execute(
            "SELECT * FROM cases WHERE case_id = ?",
            (case_id,),
        ).fetchone()
    return dict(row) if row else None


def set_needs_review(case_id: str, needs_review: bool) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE cases SET needs_review = ? WHERE case_id = ?",
            (1 if needs_review else 0, case_id),
        )


def set_case_status(
    case_id: str,
    status: str,
    *,
    updated_by: str | None = None,
    escalate_reason: str | None = None,
    return_reason: str | None = None,
    lead_note_to_agent: str | None = None,
) -> None:
    with _connect() as conn:
        _ensure_case_columns(conn)
        fields = [
            "status = ?",
            "status_updated_at = ?",
            "status_updated_by = ?",
        ]
        values: list[Any] = [status, _now(), updated_by]
        if escalate_reason is not None:
            fields.append("escalate_reason = ?")
            values.append(escalate_reason)
        if return_reason is not None:
            fields.append("return_reason = ?")
            values.append(return_reason)
        if lead_note_to_agent is not None:
            fields.append("lead_note_to_agent = ?")
            values.append(lead_note_to_agent)
        values.append(case_id)
        conn.execute(
            f"UPDATE cases SET {', '.join(fields)} WHERE case_id = ?",
            values,
        )


def assign_case(case_id: str, assigned_to: str | None, *, updated_by: str | None = None) -> None:
    with _connect() as conn:
        _ensure_case_columns(conn)
        conn.execute(
            """
            UPDATE cases
            SET assigned_to = ?, status_updated_at = ?, status_updated_by = ?
            WHERE case_id = ?
            """,
            (assigned_to, _now(), updated_by, case_id),
        )


def next_action_order(case_id: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(step_order), 0) AS m FROM actions WHERE case_id = ?",
            (case_id,),
        ).fetchone()
    return int(row["m"] if row else 0) + 1


def get_case_actions(case_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM actions WHERE case_id = ? ORDER BY step_order ASC",
            (case_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_case_messages(case_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE case_id = ? ORDER BY id ASC",
            (case_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_escalated_cases(limit: int = 50) -> list[dict[str, Any]]:
    """Open escalations for lead queue."""
    with _connect() as conn:
        _ensure_case_columns(conn)
        rows = conn.execute(
            """
            SELECT * FROM cases
            WHERE status = ?
            ORDER BY COALESCE(status_updated_at, created_at) DESC
            LIMIT ?
            """,
            (STATUS_ESCALATED, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def case_count() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM cases").fetchone()
    return int(row["c"] if row else 0)


def sla_remaining(sla_due_at: str | None) -> str:
    """Human countdown for SLA clock (ticks on each page rerun)."""
    if not sla_due_at:
        return "—"
    try:
        due = datetime.fromisoformat(sla_due_at)
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
    except ValueError:
        return "—"
    delta = due - datetime.now(timezone.utc)
    secs = int(delta.total_seconds())
    if secs < 0:
        overdue = -secs
        h, rem = divmod(overdue, 3600)
        m = rem // 60
        return f"OVERDUE {h}h {m}m" if h else f"OVERDUE {m}m"
    h, rem = divmod(secs, 3600)
    m = rem // 60
    if h >= 24:
        return f"{h // 24}d {h % 24}h left"
    return f"{h}h {m}m left" if h else f"{m}m left"


def follow_up_due_iso(hours: float | int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=float(hours))).isoformat()


def clear_all() -> None:
    with _connect() as conn:
        conn.executescript(
            "DELETE FROM messages; DELETE FROM actions; DELETE FROM cases;"
        )
