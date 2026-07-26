#!/usr/bin/env python3
"""Build PulseDesk_Summary.pdf — fixed 5-slide deck (no reportlab dependency)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_REPO = ROOT.parent.parent / "docs" / "PulseDesk_Summary.pdf"

LIVE = "https://pulsedesk-firstsource.streamlit.app"
GITHUB = "https://github.com/samkrish13/FirstSourcePOC"

# Landscape A4 in points
W, H = 841.89, 595.28

SLIDES: list[tuple[str, list[str]]] = [
    (
        "1. Problem",
        [
            "Telecom BPO teams manually read every inbox item - slow, inconsistent, judgment-heavy.",
            "Billing, outages, escalations, SIM/port, plan changes, and FAQs need different remediation paths.",
            "SLA leakage and rework rise when routing depends on individual agent interpretation.",
            "Ops leaders need auditable proof that AI can classify AND execute branch-specific actions.",
        ],
    ),
    (
        "2. Solution - PulseDesk",
        [
            "AI intake console: classify -> branch playbook -> remediate -> log (Streamlit + LLM/heuristic + SQLite).",
            "Structured classification: type, urgency, sentiment, entities, confidence.",
            "Governance gate: confidence < 65% parks cases On hold / Needs Review before unsupervised release.",
            "Agent HITL (edit / release / escalate) and Tech Lead queue (acknowledge / approve / return).",
            "Simulated tickets, holds, notifications, and follow-ups with a durable case audit trail.",
        ],
    ),
    (
        "3. Workflow design (6 branches)",
        [
            "Billing dispute: provisional hold -> Billing ticket -> 48h follow-up -> acknowledgment draft.",
            "Service outage: bulletin match -> SLA/ETA reply OR Network Ops ticket if unmatched.",
            "Complaint / escalation: P1 Retention case -> Team Lead notify -> same-day callback -> recovery draft.",
            "SIM / port: identity checklist -> Port/SIM ticket -> 24h status follow-up.",
            "Plan change: eligibility -> catalog quote -> Care order -> confirmation follow-up.",
            "General enquiry: FAQ / self-serve -> light ticket -> close-or-route disposition.",
            "Every branch emits response + route + follow-up + Case Log persistence.",
        ],
    ),
    (
        "4. Demo outcomes",
        [
            "Six golden samples (REQ-001 ... REQ-006) each trigger a distinct remediation timeline.",
            "Panel path: REQ-001 billing, REQ-002 outage, REQ-003 escalation - three branches under 3 minutes.",
            "Edge samples show the confidence gate (Needs Review / escalate to lead).",
            "Case Log proves classification, actions, and drafts are persisted for audit.",
            "Illustrative KPI: manual ~12 min first action -> assisted ~90 seconds (POC estimate).",
            f"Live demo: {LIVE}",
            f"GitHub: {GITHUB}",
            "Backup: <=3 min screen recording if Cloud is unavailable (PulseDesk_Demo_Script.md).",
        ],
    ),
    (
        "5. Scale path",
        [
            "Connect real email / CRM / ITSM (ServiceNow, Salesforce) via production orchestration.",
            "Evaluation harness: labeled inbox set, precision/recall by branch, drift monitors.",
            "Human-in-the-loop for P1 and low-confidence; four-eyes on goodwill credits.",
            "Expand to chat / voice transcripts with the same remediation contracts.",
            "Hardening: OAuth mailbox, outbound send on release, role-based SSO.",
        ],
    ),
]


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str, width: int = 95) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        trial = (" ".join(cur + [w])).strip()
        if len(trial) <= width:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return lines or [""]


def _page_stream(title: str, bullets: list[str], page_no: int) -> str:
    parts = [
        "2 J",
        "0.57 w",
        "0.1686 0.4235 0.6902 rg",
        f"0.00 {H:.2f} {W:.2f} -22.68 re f",
        "BT /F1 28.00 Tf ET",
        f"q BT 53.86 507.51 Td 0.1216 0.1608 0.2 rg ({_esc(title)}) Tj ET Q",
        "0.8471 0.8627 0.8902 RG",
        "1.13 w",
        "51.02 487.56 m 790.87 487.56 l S",
        "BT /F2 13.00 Tf ET",
    ]
    y = 450.0
    for bullet in bullets:
        lines = _wrap(bullet, 92)
        parts.append(f"q BT 65.20 {y:.2f} Td 0.1216 0.1608 0.2 rg (-) Tj ET Q")
        for i, line in enumerate(lines):
            yy = y - (i * 16)
            parts.append(
                f"q BT 82.20 {yy:.2f} Td 0.1216 0.1608 0.2 rg ({_esc(line)}) Tj ET Q"
            )
        y -= 16 * len(lines) + 14
        if y < 70:
            break
    parts.extend(
        [
            "BT /F2 8.00 Tf ET",
            "q BT 31.18 30.20 Td 0.3569 0.3961 0.4392 rg "
            "(PulseDesk POC | Incoming Request Processing Workflow | Confidential demo) Tj ET Q",
            f"q BT 790.69 30.20 Td 0.3569 0.3961 0.4392 rg ({page_no} of 5) Tj ET Q",
        ]
    )
    return "\n".join(parts)


def build(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    streams = [
        _page_stream(title, bullets, i).encode("latin-1", "replace")
        for i, (title, bullets) in enumerate(SLIDES, start=1)
    ]

    objects: list[bytes] = []
    # 1: Pages
    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(5))
    objects.append(
        f"<< /Type /Pages /Count 5 /Kids [{kids}] "
        f"/MediaBox [0 0 {W:.2f} {H:.2f}] >>".encode()
    )
    # 2: Catalog
    objects.append(b"<< /Type /Catalog /Pages 1 0 R /PageLayout /OneColumn >>")

    for i, stream in enumerate(streams):
        page_obj = 3 + i * 2
        content_obj = page_obj + 1
        objects.append(
            f"<< /Type /Page /Parent 1 0 R /Contents {content_obj} 0 R "
            f"/Resources << /Font << /F1 {13} 0 R /F2 {14} 0 R >> >> >>".encode()
        )
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )

    # fonts 13, 14
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    # Assemble PDF
    out = bytearray(b"%PDF-1.3\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode())
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 2 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n".encode()
    )
    path.write_bytes(bytes(out))


def main() -> None:
    OUT_REPO.parent.mkdir(parents=True, exist_ok=True)
    build(OUT_REPO)
    print(f"Wrote {OUT_REPO} ({OUT_REPO.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
