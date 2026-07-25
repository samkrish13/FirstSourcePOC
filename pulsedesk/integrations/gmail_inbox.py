"""Gmail inbound → PulseDesk work inbox (IMAP).

Mailbox: examplefirstsource@gmail.com

Requires a Google App Password (not the normal login password):
  Google Account → Security → 2-Step Verification → App passwords
Store it in `.streamlit/secrets.toml` or `.env` — never commit it.
"""

from __future__ import annotations

import email
import hashlib
import imaplib
import os
import re
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Any

from dotenv import load_dotenv

load_dotenv()

MAILBOX_ADDRESS = "examplefirstsource@gmail.com"
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


def _secrets_gmail() -> dict[str, Any]:
    try:
        import streamlit as st

        block = st.secrets.get("gmail", {})
        if hasattr(block, "to_dict"):
            return dict(block.to_dict())
        return dict(block) if block else {}
    except Exception:
        return {}


def gmail_credentials() -> tuple[str, str] | None:
    """Return (address, app_password) or None if not configured."""
    sec = _secrets_gmail()
    address = (
        str(sec.get("address") or "").strip()
        or os.getenv("GMAIL_ADDRESS", "").strip()
        or MAILBOX_ADDRESS
    )
    password = (
        str(sec.get("app_password") or "").strip()
        or os.getenv("GMAIL_APP_PASSWORD", "").strip()
    )
    password = password.replace(" ", "")
    if not password:
        return None
    return address, password


def gmail_configured() -> bool:
    return gmail_credentials() is not None


def mailbox_address() -> str:
    creds = gmail_credentials()
    if creds:
        return creds[0]
    return MAILBOX_ADDRESS


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


def fetch_inbox_messages(*, limit: int = 20, unseen_only: bool = False) -> list[dict[str, Any]]:
    """Pull recent messages from the linked Gmail inbox via IMAP."""
    creds = gmail_credentials()
    if not creds:
        raise RuntimeError(
            "Gmail is not configured. Set gmail.app_password in "
            ".streamlit/secrets.toml (or GMAIL_APP_PASSWORD in .env)."
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
    limit: int = 15,
    unseen_only: bool = False,
    actor: str = "gmail-sync",
) -> dict[str, Any]:
    """Fetch Gmail messages and create PulseDesk cases (skip duplicates)."""
    import db
    from workflows.pipeline import process_request

    mailbox = mailbox_address()
    messages = fetch_inbox_messages(limit=limit, unseen_only=unseen_only)
    created: list[str] = []
    skipped: list[str] = []
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
            f"Message-ID: {mid}\n\n"
            f"{item.get('body') or ''}"
        ).strip()
        try:
            result = process_request(
                subject,
                body,
                request_id=req_id,
                assigned_to=None,
                actor=actor,
            )
            created.append(str(result.get("case_id") or case_id))
        except Exception as exc:  # noqa: BLE001 — surface per-message sync errors
            errors.append(f"{mid}: {exc}")

    return {
        "mailbox": mailbox,
        "fetched": len(messages),
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }
