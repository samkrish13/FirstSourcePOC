"""Gmail inbound (IMAP) + optional outbound reply (SMTP).

Supports one or many mailboxes via secrets / env / in-app connect.

Requires a Google App Password (not the normal login password):
  Google Account → Security → 2-Step Verification → App passwords
Store credentials in `.streamlit/secrets.toml` or `.env` — never commit them.
"""

from __future__ import annotations

import email
import hashlib
import imaplib
import os
import re
import smtplib
from email.header import decode_header
from email.message import EmailMessage, Message
from email.utils import parsedate_to_datetime
from typing import Any

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MAILBOX = "examplefirstsource@gmail.com"
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

_FROM_LINE_RE = re.compile(r"(?im)^From:\s*(.+?)\s*$")
_MSG_ID_LINE_RE = re.compile(r"(?im)^Message-ID:\s*(.+?)\s*$")
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


def _secrets_root() -> dict[str, Any]:
    try:
        import streamlit as st

        # Prefer nested mapping access without assuming AttrDict shape
        return dict(st.secrets)  # type: ignore[arg-type]
    except Exception:
        return {}


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        try:
            return dict(value.to_dict())
        except Exception:
            pass
    if isinstance(value, dict):
        return dict(value)
    try:
        return dict(value)
    except Exception:
        return {}


def list_mailboxes(*, connected_only: bool = True) -> list[dict[str, str]]:
    """Mailboxes ready to sync: in-app connected accounts + optional secrets."""
    found: list[dict[str, str]] = []

    # 1) In-app authenticated mailboxes (preferred)
    try:
        import db as _db

        _db.init_db()
        for row in _db.list_linked_mailbox_rows():
            status = str(row.get("status") or "")
            password = str(row.get("app_password") or "").replace(" ", "")
            address = str(row.get("address") or "").strip()
            if not address:
                continue
            if connected_only and (
                status != _db.MAILBOX_CONNECTED or not password
            ):
                continue
            if not connected_only and status == _db.MAILBOX_DISCONNECTED:
                continue
            if not password and connected_only:
                continue
            found.append(
                {
                    "id": str(row["id"]),
                    "label": str(row.get("label") or address),
                    "address": address,
                    "app_password": password,
                    "status": status,
                    "source": "app",
                }
            )
    except Exception:
        pass

    # 2) Secrets / env fallback (ops bootstrap)
    secrets = _secrets_root()
    gmail = _as_dict(secrets.get("gmail"))
    accounts = _as_dict(gmail.get("accounts"))
    if accounts:
        for key, raw in accounts.items():
            block = _as_dict(raw)
            address = str(block.get("address") or "").strip()
            password = str(block.get("app_password") or "").strip().replace(" ", "")
            if not address or not password:
                continue
            label = str(block.get("label") or key or address).strip()
            found.append(
                {
                    "id": f"secret:{key}",
                    "label": label,
                    "address": address,
                    "app_password": password,
                    "status": "connected",
                    "source": "secrets",
                }
            )
    elif not found:
        address = (
            str(gmail.get("address") or "").strip()
            or os.getenv("GMAIL_ADDRESS", "").strip()
        )
        password = (
            str(gmail.get("app_password") or "").strip()
            or os.getenv("GMAIL_APP_PASSWORD", "").strip()
        ).replace(" ", "")
        if address and password:
            found.append(
                {
                    "id": "secret:default",
                    "label": str(gmail.get("label") or "Primary").strip(),
                    "address": address,
                    "app_password": password,
                    "status": "connected",
                    "source": "secrets",
                }
            )

    extra = os.getenv("GMAIL_ACCOUNTS", "").strip()
    if extra:
        for i, chunk in enumerate(extra.split(";")):
            parts = [p.strip() for p in chunk.split("|")]
            if len(parts) == 3 and parts[1] and parts[2]:
                label, address, password = parts
                found.append(
                    {
                        "id": f"env{i}",
                        "label": label or address,
                        "address": address,
                        "app_password": password.replace(" ", ""),
                        "status": "connected",
                        "source": "env",
                    }
                )
            elif len(parts) == 2 and parts[0] and parts[1]:
                address, password = parts
                found.append(
                    {
                        "id": f"env{i}",
                        "label": address,
                        "address": address,
                        "app_password": password.replace(" ", ""),
                        "status": "connected",
                        "source": "env",
                    }
                )

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for box in found:
        key = box["address"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(box)
    return out


def gmail_configured() -> bool:
    return bool(list_mailboxes(connected_only=True))


def mailbox_address() -> str:
    boxes = list_mailboxes(connected_only=True)
    if boxes:
        return boxes[0]["address"]
    return DEFAULT_MAILBOX


def get_mailbox(mailbox_id: str | None = None) -> dict[str, str] | None:
    boxes = list_mailboxes(connected_only=True)
    if not boxes:
        return None
    if mailbox_id:
        for box in boxes:
            if box["id"] == mailbox_id or box["address"] == mailbox_id:
                return box
    return boxes[0]


def gmail_credentials(mailbox_id: str | None = None) -> tuple[str, str] | None:
    box = get_mailbox(mailbox_id)
    if not box:
        return None
    return box["address"], box["app_password"]


def verify_imap_login(address: str, app_password: str) -> tuple[bool, str]:
    """Try Gmail IMAP login. Returns (ok, message)."""
    password = (app_password or "").replace(" ", "").strip()
    addr = (address or "").strip()
    if not addr or not password:
        return False, "Email and app password are required."
    client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        client.login(addr, password)
        client.select("INBOX")
        return True, "Mailbox authenticated successfully."
    except imaplib.IMAP4.error as exc:
        return False, f"Gmail rejected the login: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not reach Gmail: {exc}"
    finally:
        try:
            client.logout()
        except Exception:
            pass


def complete_mailbox_auth(mailbox_id: str, app_password: str) -> tuple[bool, str]:
    """Save app password, verify IMAP, mark connected or failed."""
    import db as _db

    row = _db.get_mailbox_row(mailbox_id)
    if not row:
        return False, "Mailbox invite not found."
    try:
        _db.save_mailbox_password(mailbox_id, app_password)
    except ValueError as exc:
        return False, str(exc)
    ok, msg = verify_imap_login(str(row["address"]), app_password)
    if ok:
        _db.set_mailbox_status(
            mailbox_id,
            _db.MAILBOX_CONNECTED,
            detail="Connected — ready to Sync Gmail.",
        )
        return True, msg
    _db.set_mailbox_status(
        mailbox_id,
        _db.MAILBOX_FAILED,
        detail=msg,
        clear_password=True,
    )
    return False, msg


def _decode_mime(value: str | None) -> str:
    if not value:
        return ""
    parts: list[str] = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(chunk))
    return "".join(parts).strip()


def _body_from_message(msg: Message) -> str:
    if msg.is_multipart():
        plain = ""
        html = ""
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp.lower():
                continue
            try:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ctype == "text/plain" and not plain:
                plain = text
            elif ctype == "text/html" and not html:
                html = text
        if plain:
            return plain.strip()
        if html:
            return re.sub(r"<[^>]+>", " ", html)
        return ""
    try:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace").strip()
    except Exception:
        return str(msg.get_payload() or "").strip()


def _request_id_for_message(message_id: str) -> str:
    digest = hashlib.sha1(message_id.encode("utf-8")).hexdigest()[:10].upper()
    return f"GM{digest}"


def fetch_inbox_message_ids(
    *,
    mailbox_id: str | None = None,
) -> set[str]:
    """All Message-IDs currently in the Gmail INBOX (headers only)."""
    creds = gmail_credentials(mailbox_id)
    if not creds:
        raise RuntimeError("Gmail is not configured.")
    address, password = creds
    client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        client.login(address, password)
        client.select("INBOX")
        status, data = client.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            return set()
        ids = data[0].split()
        found: set[str] = set()
        for num in ids:
            status, msg_data = client.fetch(
                num, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID MESSAGE-ID)])"
            )
            if status != "OK" or not msg_data:
                continue
            raw = b""
            for part in msg_data:
                if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], (bytes, bytearray)):
                    raw = bytes(part[1])
                    break
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            mid = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip()
            if mid:
                found.add(mid)
            else:
                found.add(f"imap-{address}-{num.decode() if isinstance(num, bytes) else num}")
        return found
    finally:
        try:
            client.logout()
        except Exception:
            pass


def fetch_inbox_messages(
    *,
    mailbox_id: str | None = None,
    limit: int = 20,
    unseen_only: bool = False,
) -> list[dict[str, Any]]:
    """Pull recent messages from a linked Gmail inbox via IMAP."""
    creds = gmail_credentials(mailbox_id)
    if not creds:
        raise RuntimeError(
            "Gmail is not configured. Add one or more accounts under [gmail.accounts.*] "
            "in .streamlit/secrets.toml (see secrets.toml.example)."
        )
    address, password = creds
    client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        client.login(address, password)
        client.select("INBOX")
        criteria = "UNSEEN" if unseen_only else "ALL"
        status, data = client.search(None, criteria)
        if status != "OK" or not data or not data[0]:
            return []
        ids = data[0].split()
        ids = ids[-limit:]
        out: list[dict[str, Any]] = []
        for num in reversed(ids):
            status, msg_data = client.fetch(num, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(raw)
            message_id = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip()
            if not message_id:
                message_id = f"imap-{address}-{num.decode()}"
            from_addr = _decode_mime(msg.get("From"))
            subject = _decode_mime(msg.get("Subject")) or "(no subject)"
            body = _body_from_message(msg)
            received = None
            date_hdr = msg.get("Date")
            if date_hdr:
                try:
                    received = parsedate_to_datetime(date_hdr).isoformat()
                except Exception:
                    received = None
            out.append(
                {
                    "message_id": message_id,
                    "from": from_addr,
                    "subject": subject,
                    "body": body,
                    "received_at": received,
                    "mailbox": address,
                }
            )
        return out
    finally:
        try:
            client.logout()
        except Exception:
            pass


def sync_gmail_inbox(
    *,
    mailbox_id: str | None = None,
    limit: int = 15,
    unseen_only: bool = False,
    actor: str = "gmail-sync",
    assigned_to: str | None = None,
) -> dict[str, Any]:
    """Fetch Gmail messages and create PulseDesk cases (skip duplicates)."""
    import db
    from workflows.pipeline import process_request

    box = get_mailbox(mailbox_id)
    if not box:
        raise RuntimeError("No Gmail mailbox configured.")
    mailbox = box["address"]
    messages = fetch_inbox_messages(
        mailbox_id=box["id"], limit=limit, unseen_only=unseen_only
    )
    created: list[str] = []
    skipped: list[str] = []
    deleted: list[str] = []
    errors: list[str] = []

    for item in messages:
        mid = item["message_id"]
        req_id = _request_id_for_message(mid)
        case_id = f"CASE-{req_id}"
        if db.get_case(case_id):
            skipped.append(case_id)
            continue
        subject = item.get("subject") or "(no subject)"
        from_addr = item.get("from") or "unknown"
        body = (
            f"From: {from_addr}\n"
            f"To: {mailbox}\n"
            f"Mailbox: {box.get('label') or mailbox}\n"
            f"Message-ID: {mid}\n\n"
            f"{item.get('body') or ''}"
        ).strip()
        try:
            result = process_request(
                subject,
                body,
                request_id=req_id,
                assigned_to=assigned_to,
                actor=actor,
            )
            cid = str(result.get("case_id") or case_id)
            db.set_source_mailbox(cid, mailbox)
            # Ensure ownership matches the agent who synced (process_request may omit)
            if assigned_to:
                db.assign_case(cid, assigned_to, updated_by=actor)
            created.append(cid)
        except Exception as exc:  # noqa: BLE001 — surface per-message sync errors
            errors.append(f"{mid}: {exc}")

    # Drop PulseDesk rows whose Gmail messages are no longer in INBOX
    try:
        live_ids = fetch_inbox_message_ids(mailbox_id=box["id"])
        live_case_ids = {f"CASE-{_request_id_for_message(mid)}" for mid in live_ids}
        for row in db.list_gmail_synced_cases(mailbox):
            cid = str(row.get("case_id") or "")
            if cid and cid not in live_case_ids:
                if db.delete_case(cid):
                    deleted.append(cid)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"prune-deleted: {exc}")

    return {
        "mailbox": mailbox,
        "label": box.get("label") or mailbox,
        "fetched": len(messages),
        "created": created,
        "skipped": skipped,
        "deleted": deleted,
        "errors": errors,
    }


def extract_customer_email(body: str, *, exclude: set[str] | None = None) -> str | None:
    """Pull customer address from synced body `From:` line (or first email in text)."""
    exclude_l = {e.strip().lower() for e in (exclude or set()) if e}
    blob = body or ""
    m = _FROM_LINE_RE.search(blob)
    candidates = _EMAIL_RE.findall(m.group(1) if m else blob[:800])
    for addr in candidates:
        if addr.strip().lower() not in exclude_l:
            return addr.strip()
    return None


def extract_inbound_message_id(body: str) -> str | None:
    m = _MSG_ID_LINE_RE.search(body or "")
    if not m:
        return None
    mid = m.group(1).strip()
    return mid or None


def send_reply(
    *,
    to_addr: str,
    subject: str,
    body: str,
    mailbox_id: str | None = None,
    in_reply_to: str | None = None,
) -> dict[str, Any]:
    """Send a real reply via Gmail SMTP using a connected mailbox App Password.

    Returns {{ok, simulated, detail, from, to, mailbox_id}}.
    """
    to_addr = (to_addr or "").strip()
    if not to_addr or "@" not in to_addr:
        return {
            "ok": False,
            "simulated": True,
            "detail": "No customer email on this case — release logged as simulated.",
            "from": None,
            "to": None,
            "mailbox_id": mailbox_id,
        }

    box = get_mailbox(mailbox_id)
    if not box:
        return {
            "ok": False,
            "simulated": True,
            "detail": "No connected Gmail mailbox — release logged as simulated.",
            "from": None,
            "to": to_addr,
            "mailbox_id": mailbox_id,
        }

    from_addr = str(box["address"]).strip()
    password = str(box.get("app_password") or "").replace(" ", "").strip()
    if not password:
        return {
            "ok": False,
            "simulated": True,
            "detail": f"Mailbox {from_addr} has no App Password — simulated release.",
            "from": from_addr,
            "to": to_addr,
            "mailbox_id": box["id"],
        }

    subj = (subject or "").strip() or "(no subject)"
    if not re.match(r"(?i)^re:\s*", subj):
        subj = f"Re: {subj}"

    msg = EmailMessage()
    msg["Subject"] = subj
    msg["From"] = from_addr
    msg["To"] = to_addr
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body or "")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(from_addr, password)
            smtp.send_message(msg)
        return {
            "ok": True,
            "simulated": False,
            "detail": f"Sent from {from_addr} → {to_addr}",
            "from": from_addr,
            "to": to_addr,
            "mailbox_id": box["id"],
            "subject": subj,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "simulated": True,
            "detail": f"SMTP send failed ({exc}); release logged as simulated.",
            "from": from_addr,
            "to": to_addr,
            "mailbox_id": box["id"],
        }


def try_send_case_release(
    case: dict[str, Any] | None,
    draft: str,
    *,
    mailbox_id: str | None = None,
) -> dict[str, Any]:
    """Best-effort real send for Release / Approve using case body + connected mailbox."""
    case = case or {}
    body = str(case.get("body") or "")
    source_mb = str(case.get("source_mailbox") or "").strip()
    boxes = list_mailboxes(connected_only=True)
    chosen_id = mailbox_id
    if not chosen_id and source_mb:
        for b in boxes:
            if b.get("address", "").lower() == source_mb.lower():
                chosen_id = b["id"]
                break
    if not chosen_id and boxes:
        chosen_id = boxes[0]["id"]

    exclude = {source_mb} if source_mb else set()
    for b in boxes:
        exclude.add(str(b.get("address") or ""))

    to_addr = extract_customer_email(body, exclude=exclude)
    in_reply_to = extract_inbound_message_id(body)
    return send_reply(
        to_addr=to_addr or "",
        subject=str(case.get("subject") or ""),
        body=draft or "",
        mailbox_id=chosen_id,
        in_reply_to=in_reply_to,
    )
